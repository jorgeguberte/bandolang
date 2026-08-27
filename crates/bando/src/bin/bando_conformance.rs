use std::io::{self, Read};
use bando::{run_conformance, ConformanceProgramV0};

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let input_str = if args.len() > 1 {
        std::fs::read_to_string(&args[1]).expect("Failed to read input file")
    } else {
        let mut buffer = String::new();
        io::stdin()
            .read_to_string(&mut buffer)
            .expect("Failed to read from stdin");
        buffer
    };

    let prog: ConformanceProgramV0 = serde_json::from_str(&input_str).expect("Failed to parse ConformanceProgramV0 JSON");
    let obs = run_conformance(&prog);
    let output_json = serde_json::to_string_pretty(&obs).expect("Failed to serialize ConformanceObservationV0");
    println!("{}", output_json);
}
