use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

#[derive(Debug, Clone, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
pub struct BudgetResourceId(pub String);

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum BudgetError {
    InsufficientAvailable {
        resource: String,
        needed: u64,
        available: u64,
    },
    InsufficientReserved {
        resource: String,
        needed: u64,
        reserved: u64,
    },
    OutstandingCommitmentsBlockSettlement {
        reserved: u64,
    },
    DuplicateSettlement,
}

impl std::fmt::Display for BudgetError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            BudgetError::InsufficientAvailable {
                resource,
                needed,
                available,
            } => {
                write!(
                    f,
                    "Insufficient available budget for resource '{}': needed {}, available {}",
                    resource, needed, available
                )
            }
            BudgetError::InsufficientReserved {
                resource,
                needed,
                reserved,
            } => {
                write!(
                    f,
                    "Insufficient reserved budget for resource '{}': needed {}, reserved {}",
                    resource, needed, reserved
                )
            }
            BudgetError::OutstandingCommitmentsBlockSettlement { reserved } => {
                write!(
                    f,
                    "Outstanding commitments (reserved: {}) block settlement",
                    reserved
                )
            }
            BudgetError::DuplicateSettlement => {
                write!(f, "Duplicate settlement on already settled frame")
            }
        }
    }
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct FrameBudget {
    pub available: BTreeMap<String, u64>,
    pub reserved: BTreeMap<String, u64>,
    pub spent: BTreeMap<String, u64>,
}

impl FrameBudget {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn with_initial(resource: impl Into<String>, amount: u64) -> Self {
        let mut b = Self::default();
        b.available.insert(resource.into(), amount);
        b
    }

    pub fn get_available(&self, resource: &str) -> u64 {
        *self.available.get(resource).unwrap_or(&0)
    }

    pub fn get_reserved(&self, resource: &str) -> u64 {
        *self.reserved.get(resource).unwrap_or(&0)
    }

    pub fn get_spent(&self, resource: &str) -> u64 {
        *self.spent.get(resource).unwrap_or(&0)
    }

    pub fn has_outstanding_commitments(&self) -> bool {
        self.reserved.values().any(|&amt| amt > 0)
    }

    // Section 18: parent.available -= grant; child.available += grant (Atomic transfer)
    pub fn transfer_to_child(
        &mut self,
        resource: &str,
        grant: u64,
        child: &mut FrameBudget,
    ) -> Result<(), BudgetError> {
        let avail = self.get_available(resource);
        if avail < grant {
            return Err(BudgetError::InsufficientAvailable {
                resource: resource.to_string(),
                needed: grant,
                available: avail,
            });
        }

        self.available.insert(resource.to_string(), avail - grant);
        let child_avail = child.get_available(resource);
        child
            .available
            .insert(resource.to_string(), child_avail + grant);
        Ok(())
    }

    // Section 20: parent.available += child.unspent; child.spent stays in child
    pub fn settle_from_child(
        &mut self,
        child: &mut FrameBudget,
    ) -> Result<BTreeMap<String, u64>, BudgetError> {
        if child.has_outstanding_commitments() {
            let total_res: u64 = child.reserved.values().sum();
            return Err(BudgetError::OutstandingCommitmentsBlockSettlement {
                reserved: total_res,
            });
        }

        let mut refunded = BTreeMap::new();
        for (res, &child_unspent) in &child.available {
            if child_unspent > 0 {
                let parent_avail = self.get_available(res);
                self.available
                    .insert(res.clone(), parent_avail + child_unspent);
                refunded.insert(res.clone(), child_unspent);
            }
        }
        child.available.clear();
        Ok(refunded)
    }

    pub fn reserve(&mut self, resource: &str, amount: u64) -> Result<(), BudgetError> {
        let avail = self.get_available(resource);
        if avail < amount {
            return Err(BudgetError::InsufficientAvailable {
                resource: resource.to_string(),
                needed: amount,
                available: avail,
            });
        }
        self.available.insert(resource.to_string(), avail - amount);
        let res = self.get_reserved(resource);
        self.reserved.insert(resource.to_string(), res + amount);
        Ok(())
    }

    pub fn spend_reserved(&mut self, resource: &str, amount: u64) -> Result<(), BudgetError> {
        let res = self.get_reserved(resource);
        if res < amount {
            return Err(BudgetError::InsufficientReserved {
                resource: resource.to_string(),
                needed: amount,
                reserved: res,
            });
        }
        self.reserved.insert(resource.to_string(), res - amount);
        let sp = self.get_spent(resource);
        self.spent.insert(resource.to_string(), sp + amount);
        Ok(())
    }

    pub fn spend_direct(&mut self, resource: &str, amount: u64) -> Result<(), BudgetError> {
        let avail = self.get_available(resource);
        if avail < amount {
            return Err(BudgetError::InsufficientAvailable {
                resource: resource.to_string(),
                needed: amount,
                available: avail,
            });
        }
        self.available.insert(resource.to_string(), avail - amount);
        let sp = self.get_spent(resource);
        self.spent.insert(resource.to_string(), sp + amount);
        Ok(())
    }
}
