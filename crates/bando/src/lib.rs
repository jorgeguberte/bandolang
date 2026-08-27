pub mod analysis;
pub mod conformance;
pub mod diagnostics;
pub mod gate;
pub mod ir;
pub mod lowering;
pub mod printer;
pub mod registry;
pub mod verifier;
pub mod vm;
pub mod vm_ir;
pub mod vm_verifier;
pub mod world;

pub use conformance::{run_conformance, ConformanceObservationV0, ConformanceProgramV0};
pub use diagnostics::{Diagnostic, DiagnosticCode};
pub use ir::{Block, Effect, EffectRow, Fact, FactArg, Function, Instruction, Module, Terminator, Type, Value, ValueId};
pub use registry::{AtomicityGuarantee, MutationFootprint, OperationDescriptor, OperationId, PolicyRequirement, RegistrySnapshot, TrustPolicy, VerifierDescriptor, VerifierId};
pub use world::{WorldError, WorldState};
