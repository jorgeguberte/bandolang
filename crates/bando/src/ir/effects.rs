use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;
use std::fmt;

#[derive(Debug, Clone, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
pub enum Effect {
    Read(String),
    Infer,
    Act(String),
}

impl fmt::Display for Effect {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Effect::Read(d) => write!(f, "read[{}]", d),
            Effect::Infer => write!(f, "infer"),
            Effect::Act(d) => write!(f, "act[{}]", d),
        }
    }
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
pub struct EffectRow {
    pub effects: BTreeSet<Effect>,
}

impl EffectRow {
    pub fn empty() -> Self {
        Self {
            effects: BTreeSet::new(),
        }
    }

    pub fn with(mut self, eff: Effect) -> Self {
        self.effects.insert(eff);
        self
    }

    pub fn contains(&self, eff: &Effect) -> bool {
        self.effects.contains(eff)
    }

    pub fn is_subset(&self, other: &EffectRow) -> bool {
        self.effects.is_subset(&other.effects)
    }

    pub fn union(&self, other: &EffectRow) -> Self {
        let mut merged = self.effects.clone();
        merged.extend(other.effects.iter().cloned());
        Self { effects: merged }
    }
}
