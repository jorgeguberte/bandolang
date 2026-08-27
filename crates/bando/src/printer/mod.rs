use crate::ir::{Function, Module};
use crate::vm_ir::{VmFunction, VmModule};

pub struct IrPrinter;

impl IrPrinter {
    pub fn print_module(module: &Module) -> String {
        let mut out = format!("module @{} {{\n", module.name);
        for func in &module.functions {
            out.push_str(&Self::print_function(func));
        }
        out.push_str("}\n");
        out
    }

    pub fn print_function(func: &Function) -> String {
        let mut out = format!("  func @{}(", func.name);
        let params: Vec<_> = func
            .params
            .iter()
            .map(|(p, t)| format!("%v{}: {}", p.0, t.display_name()))
            .collect();
        out.push_str(&params.join(", "));
        out.push_str(&format!(") -> {} {{\n", func.return_type.display_name()));

        for (block_id, block) in &func.blocks {
            out.push_str(&format!("    ^bb{}:\n", block_id.0));
            for inst in &block.instructions {
                out.push_str(&format!("      {:?}\n", inst));
            }
            out.push_str(&format!("      {:?}\n", block.terminator));
        }
        out.push_str("  }\n");
        out
    }

    pub fn print_vm_module(module: &VmModule) -> String {
        let mut out = format!("vm_module @{} {{\n", module.name);
        for func in &module.functions {
            out.push_str(&Self::print_vm_function(func));
        }
        out.push_str("}\n");
        out
    }

    pub fn print_vm_function(func: &VmFunction) -> String {
        let mut out = format!("  vm_func @{}(", func.name);
        let params: Vec<_> = func
            .params
            .iter()
            .map(|(p, t)| format!("%v{}: {}", p.0, t.display_name()))
            .collect();
        out.push_str(&params.join(", "));
        out.push_str(&format!(") -> {} {{\n", func.return_type.display_name()));

        for (block_id, block) in &func.blocks {
            out.push_str(&format!("    ^bb{}:\n", block_id.0));
            for inst in &block.instructions {
                out.push_str(&format!("      {:?}\n", inst));
            }
            out.push_str(&format!("      {:?}\n", block.terminator));
        }
        out.push_str("  }\n");
        out
    }
}
