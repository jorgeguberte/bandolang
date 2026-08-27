use std::collections::BTreeMap;
use crate::ir::values::Value as VmValue;

pub trait ReadAdapter: Send + Sync {
    fn read(&self, domain: &str) -> Result<VmValue, VmValue>;
}

pub trait InferAdapter: Send + Sync {
    fn infer(&self, prompt: &str) -> Result<VmValue, VmValue>;
}

#[derive(Default)]
pub struct DefaultTestReadAdapter {
    pub errors: BTreeMap<String, String>,
}

impl ReadAdapter for DefaultTestReadAdapter {
    fn read(&self, domain: &str) -> Result<VmValue, VmValue> {
        if let Some(err) = self.errors.get(domain) {
            Err(VmValue::String(err.clone()))
        } else {
            Ok(VmValue::String(format!("data_of({})", domain)))
        }
    }
}

#[derive(Default)]
pub struct DefaultTestInferAdapter {
    pub errors: BTreeMap<String, String>,
}

impl InferAdapter for DefaultTestInferAdapter {
    fn infer(&self, prompt: &str) -> Result<VmValue, VmValue> {
        if let Some(err) = self.errors.get(prompt) {
            Err(VmValue::String(err.clone()))
        } else {
            Ok(VmValue::String(format!("infer_of({})", prompt)))
        }
    }
}

pub struct RuntimeAdapters {
    pub read: Box<dyn ReadAdapter>,
    pub infer: Box<dyn InferAdapter>,
}

impl Default for RuntimeAdapters {
    fn default() -> Self {
        Self {
            read: Box::new(DefaultTestReadAdapter::default()),
            infer: Box::new(DefaultTestInferAdapter::default()),
        }
    }
}
