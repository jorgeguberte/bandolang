use std::collections::{BTreeMap, BTreeSet, VecDeque};

use crate::{
    ir::facts::{ActLatentPostconditions, Fact, FactArg, LatentPostconditions},
    lowering::CompilerMutations,
    vm_ir::{VmBlockId, VmFunction, VmInstruction, VmTerminator, VmValueId},
};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AnalysisResult {
    pub block_in_facts: BTreeMap<VmBlockId, BTreeSet<Fact>>,
    pub block_out_facts: BTreeMap<VmBlockId, BTreeSet<Fact>>,
    pub edge_facts: BTreeMap<(VmBlockId, VmBlockId), BTreeSet<Fact>>,
}

pub struct PathFactAnalyzer<'a> {
    func: &'a VmFunction,
    mutations: CompilerMutations,
}

impl<'a> PathFactAnalyzer<'a> {
    pub fn new(func: &'a VmFunction) -> Self {
        Self {
            func,
            mutations: CompilerMutations::default(),
        }
    }

    pub fn with_mutations(func: &'a VmFunction, mutations: CompilerMutations) -> Self {
        Self { func, mutations }
    }

    pub fn analyze(&self) -> AnalysisResult {
        let mut var_latent: BTreeMap<VmValueId, LatentPostconditions> = BTreeMap::new();
        let mut act_latent: BTreeMap<VmValueId, ActLatentPostconditions> = BTreeMap::new();

        // Collect latent metadata from instructions
        for block in self.func.blocks.values() {
            for inst in &block.instructions {
                match inst {
                    VmInstruction::VmRead { dest, latent, .. } => {
                        var_latent.insert(*dest, latent.clone());
                    }
                    VmInstruction::VmInfer { dest, latent, .. } => {
                        var_latent.insert(*dest, latent.clone());
                    }
                    VmInstruction::VmAct { dest, latent, .. } => {
                        act_latent.insert(*dest, latent.clone());
                    }
                    VmInstruction::VmAssign { dest, source, .. } => {
                        if let Some(lat) = var_latent.get(source) {
                            var_latent.insert(*dest, lat.clone());
                        }
                        if let Some(lat) = act_latent.get(source) {
                            act_latent.insert(*dest, lat.clone());
                        }
                    }
                    _ => {}
                }
            }
        }

        let mut block_in_facts: BTreeMap<VmBlockId, BTreeSet<Fact>> = BTreeMap::new();
        let mut block_out_facts: BTreeMap<VmBlockId, BTreeSet<Fact>> = BTreeMap::new();
        let mut edge_facts: BTreeMap<(VmBlockId, VmBlockId), BTreeSet<Fact>> = BTreeMap::new();

        for block_id in self.func.blocks.keys() {
            let mut init_facts = BTreeSet::new();
            if self.mutations.m05_eager_on_ok_materialization && *block_id == self.func.entry {
                for latent in var_latent.values() {
                    for f in latent.instantiate_ok("v_eager") {
                        init_facts.insert(f);
                    }
                }
            }
            block_in_facts.insert(*block_id, init_facts);
            block_out_facts.insert(*block_id, BTreeSet::new());
        }

        let mut worklist: VecDeque<VmBlockId> = VecDeque::new();
        let mut visited: BTreeSet<VmBlockId> = BTreeSet::new();

        worklist.push_back(self.func.entry);

        while let Some(curr_id) = worklist.pop_front() {
            if self.mutations.m10_single_pass_loop_analysis && visited.contains(&curr_id) {
                continue;
            }
            visited.insert(curr_id);

            let block = if let Some(b) = self.func.blocks.get(&curr_id) {
                b
            } else {
                continue;
            };

            let in_facts = block_in_facts.get(&curr_id).cloned().unwrap_or_default();
            let out_facts = in_facts.clone();
            block_out_facts.insert(curr_id, out_facts.clone());

            let succ_edges = self.compute_successor_edges(
                curr_id,
                &block.terminator,
                &out_facts,
                &var_latent,
                &act_latent,
            );

            for (succ_id, facts_on_edge) in succ_edges {
                edge_facts.insert((curr_id, succ_id), facts_on_edge);

                let incoming_facts: Vec<BTreeSet<Fact>> = self
                    .find_predecessors(succ_id)
                    .into_iter()
                    .filter_map(|pred_id| edge_facts.get(&(pred_id, succ_id)).cloned())
                    .collect();

                let new_succ_in = if incoming_facts.is_empty() {
                    BTreeSet::new()
                } else if self.mutations.m06_merge_union_facts {
                    let mut union_set = BTreeSet::new();
                    for next_set in &incoming_facts {
                        union_set.extend(next_set.iter().cloned());
                    }
                    union_set
                } else {
                    let mut intersection = incoming_facts[0].clone();
                    for next_set in &incoming_facts[1..] {
                        intersection = intersection.intersection(next_set).cloned().collect();
                    }
                    intersection
                };

                let changed = block_in_facts.get(&succ_id) != Some(&new_succ_in);
                block_in_facts.insert(succ_id, new_succ_in);

                if !visited.contains(&succ_id)
                    || (changed && !self.mutations.m10_single_pass_loop_analysis)
                {
                    if !worklist.contains(&succ_id) {
                        worklist.push_back(succ_id);
                    }
                }
            }
        }

        AnalysisResult {
            block_in_facts,
            block_out_facts,
            edge_facts,
        }
    }

    fn find_predecessors(&self, target: VmBlockId) -> Vec<VmBlockId> {
        let mut preds = Vec::new();
        for (b_id, b) in &self.func.blocks {
            if self.terminator_targets(&b.terminator).contains(&target) {
                preds.push(*b_id);
            }
        }
        preds
    }

    fn terminator_targets(&self, term: &VmTerminator) -> Vec<VmBlockId> {
        match term {
            VmTerminator::Br { target, .. } => vec![*target],
            VmTerminator::CondBr {
                true_target,
                false_target,
                ..
            } => vec![*true_target, *false_target],
            VmTerminator::SwitchResult {
                ok_target,
                err_target,
                ..
            } => vec![*ok_target, *err_target],
            VmTerminator::SwitchActOutcome {
                success_target,
                failure_target,
                partial_target,
                unknown_target,
                ..
            } => vec![
                *success_target,
                *failure_target,
                *partial_target,
                *unknown_target,
            ],
            _ => Vec::new(),
        }
    }

    fn compute_successor_edges(
        &self,
        _src: VmBlockId,
        term: &VmTerminator,
        base_facts: &BTreeSet<Fact>,
        var_latent: &BTreeMap<VmValueId, LatentPostconditions>,
        act_latent: &BTreeMap<VmValueId, ActLatentPostconditions>,
    ) -> Vec<(VmBlockId, BTreeSet<Fact>)> {
        let mut edges = Vec::new();
        match term {
            VmTerminator::Br { target, args } => {
                let target_block = if let Some(b) = self.func.blocks.get(target) {
                    b
                } else {
                    return edges;
                };
                let renaming = self.build_renaming(args, &target_block.params);
                let renamed: BTreeSet<Fact> =
                    base_facts.iter().map(|f| f.rename(&renaming)).collect();
                edges.push((*target, renamed));
            }
            VmTerminator::CondBr {
                cond,
                true_target,
                true_args,
                false_target,
                false_args,
            } => {
                if let Some(t_block) = self.func.blocks.get(true_target) {
                    let mut t_facts = base_facts.clone();
                    t_facts.insert(Fact::new(
                        "IsTrue",
                        vec![FactArg::Symbol(format!("v{}", cond.0))],
                    ));
                    let renaming = self.build_renaming(true_args, &t_block.params);
                    let renamed = t_facts.iter().map(|f| f.rename(&renaming)).collect();
                    edges.push((*true_target, renamed));
                }

                if let Some(f_block) = self.func.blocks.get(false_target) {
                    let mut f_facts = base_facts.clone();
                    f_facts.insert(Fact::new(
                        "IsFalse",
                        vec![FactArg::Symbol(format!("v{}", cond.0))],
                    ));
                    let renaming = self.build_renaming(false_args, &f_block.params);
                    let renamed = f_facts.iter().map(|f| f.rename(&renaming)).collect();
                    edges.push((*false_target, renamed));
                }
            }
            VmTerminator::SwitchResult {
                result_val,
                ok_target,
                ok_arg,
                err_target,
                err_arg,
            } => {
                let latent = var_latent.get(result_val).cloned().unwrap_or_default();

                if let Some(ok_block) = self.func.blocks.get(ok_target) {
                    let mut ok_facts = base_facts.clone();
                    ok_facts.insert(Fact::new(
                        "IsOk",
                        vec![FactArg::Symbol(format!("v{}", result_val.0))],
                    ));
                    for f in latent.instantiate_ok(&format!("v{}", ok_arg.0)) {
                        ok_facts.insert(f);
                    }
                    let renaming = self.build_renaming(&[*ok_arg], &ok_block.params);
                    let renamed = ok_facts.iter().map(|f| f.rename(&renaming)).collect();
                    edges.push((*ok_target, renamed));
                }

                if let Some(err_block) = self.func.blocks.get(err_target) {
                    let mut err_facts = base_facts.clone();
                    err_facts.insert(Fact::new(
                        "IsErr",
                        vec![FactArg::Symbol(format!("v{}", result_val.0))],
                    ));
                    for f in latent.instantiate_err(&format!("v{}", err_arg.0)) {
                        err_facts.insert(f);
                    }
                    let renaming = self.build_renaming(&[*err_arg], &err_block.params);
                    let renamed = err_facts.iter().map(|f| f.rename(&renaming)).collect();
                    edges.push((*err_target, renamed));
                }
            }
            VmTerminator::SwitchActOutcome {
                outcome_val,
                success_target,
                success_arg,
                failure_target,
                failure_arg,
                partial_target,
                partial_arg,
                unknown_target,
                unknown_arg,
            } => {
                let latent = act_latent.get(outcome_val).cloned().unwrap_or_default();

                if let Some(succ_block) = self.func.blocks.get(success_target) {
                    let mut succ_facts = base_facts.clone();
                    succ_facts.insert(Fact::new(
                        "IsSuccess",
                        vec![FactArg::Symbol(format!("v{}", outcome_val.0))],
                    ));
                    for f in latent.instantiate_success(&format!("v{}", success_arg.0)) {
                        succ_facts.insert(f);
                    }
                    let renaming = self.build_renaming(&[*success_arg], &succ_block.params);
                    let renamed = succ_facts.iter().map(|f| f.rename(&renaming)).collect();
                    edges.push((*success_target, renamed));
                }

                if let Some(fail_block) = self.func.blocks.get(failure_target) {
                    let mut fail_facts = base_facts.clone();
                    fail_facts.insert(Fact::new(
                        "IsFailure",
                        vec![FactArg::Symbol(format!("v{}", outcome_val.0))],
                    ));
                    for f in latent.instantiate_failure(&format!("v{}", failure_arg.0)) {
                        fail_facts.insert(f);
                    }
                    let renaming = self.build_renaming(&[*failure_arg], &fail_block.params);
                    let renamed = fail_facts.iter().map(|f| f.rename(&renaming)).collect();
                    edges.push((*failure_target, renamed));
                }

                if let Some(part_block) = self.func.blocks.get(partial_target) {
                    let mut part_facts = base_facts.clone();
                    part_facts.insert(Fact::new(
                        "IsPartial",
                        vec![FactArg::Symbol(format!("v{}", outcome_val.0))],
                    ));
                    for f in latent.instantiate_partial(&format!("v{}", partial_arg.0)) {
                        part_facts.insert(f);
                    }
                    if self.mutations.s2m12_success_fact_on_partial {
                        for f in latent.instantiate_success(&format!("v{}", partial_arg.0)) {
                            part_facts.insert(f);
                        }
                    }
                    let renaming = self.build_renaming(&[*partial_arg], &part_block.params);
                    let renamed = part_facts.iter().map(|f| f.rename(&renaming)).collect();
                    edges.push((*partial_target, renamed));
                }

                if let Some(unk_block) = self.func.blocks.get(unknown_target) {
                    let mut unk_facts = base_facts.clone();
                    unk_facts.insert(Fact::new(
                        "IsUnknown",
                        vec![FactArg::Symbol(format!("v{}", outcome_val.0))],
                    ));
                    let renaming = self.build_renaming(&[*unknown_arg], &unk_block.params);
                    let renamed = unk_facts.iter().map(|f| f.rename(&renaming)).collect();
                    edges.push((*unknown_target, renamed));
                }
            }
            _ => {}
        }
        edges
    }

    fn build_renaming(
        &self,
        args: &[VmValueId],
        params: &[(VmValueId, crate::ir::types::Type)],
    ) -> BTreeMap<String, String> {
        let mut map = BTreeMap::new();
        for (i, (param_id, _)) in params.iter().enumerate() {
            if i < args.len() {
                map.insert(format!("v{}", args[i].0), format!("v{}", param_id.0));
            }
        }
        map
    }
}
