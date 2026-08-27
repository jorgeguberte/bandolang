use std::collections::{BTreeMap, BTreeSet};

#[derive(Debug, Clone)]
pub struct DominanceTree<B: Copy + Ord> {
    pub dominators: BTreeMap<B, BTreeSet<B>>,
}

impl<B: Copy + Ord> DominanceTree<B> {
    pub fn compute<F>(entry: B, blocks: &[B], get_preds: F) -> Self
    where
        F: Fn(B) -> Vec<B>,
    {
        let all_blocks: BTreeSet<B> = blocks.iter().copied().collect();
        let mut dominators: BTreeMap<B, BTreeSet<B>> = BTreeMap::new();

        dominators.insert(entry, BTreeSet::from([entry]));
        for &b in blocks {
            if b != entry {
                dominators.insert(b, all_blocks.clone());
            }
        }

        let mut changed = true;
        while changed {
            changed = false;
            for &b in blocks {
                if b == entry {
                    continue;
                }

                let preds = get_preds(b);
                let reachable_preds: Vec<_> = preds
                    .into_iter()
                    .filter(|p| dominators.contains_key(p))
                    .collect();

                let new_dom = if reachable_preds.is_empty() {
                    BTreeSet::from([b])
                } else {
                    let mut inter = dominators.get(&reachable_preds[0]).cloned().unwrap_or_default();
                    for next_pred in &reachable_preds[1..] {
                        if let Some(pred_dom) = dominators.get(next_pred) {
                            inter = inter.intersection(pred_dom).copied().collect();
                        }
                    }
                    inter.insert(b);
                    inter
                };

                if dominators.get(&b) != Some(&new_dom) {
                    dominators.insert(b, new_dom);
                    changed = true;
                }
            }
        }

        Self { dominators }
    }

    pub fn dominates(&self, a: B, b: B) -> bool {
        if let Some(dom_b) = self.dominators.get(&b) {
            dom_b.contains(&a)
        } else {
            false
        }
    }
}
