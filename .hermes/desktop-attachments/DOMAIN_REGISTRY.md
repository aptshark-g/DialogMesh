# Literature Cortex — Domain Registry

> Version: 1.0  
> Source: `lcortex/seeds/l0l4_reverse_index.json`  
> Total Domains: 27  
> Total Mappings: 178 node-domain pairs  
> For DialogMesh cross-project alignment.

---

## Domain List (27)

| # | Domain ID | Mapped Nodes | Primary L0-L4 Anchor |
|---|-----------|-------------|----------------------|
| 1 | control_system | 27 | method-6 (Feedback), method-4 (Adaptive), phys-1 (Oscillation) |
| 2 | mathematics | 22 | axiom-1 (ZFC), math-3 (Optimization), math-5 (Spectral) |
| 3 | materials_science | 17 | phys-4 (Constitutive), meta-6 (Epistemic Boundary) |
| 4 | physics | 15 | phys-2 (Thermal), phys-3 (EM), phys-7 (Phase Transition) |
| 5 | biology | 11 | method-6 (Feedback), axiom-10 (Noether) |
| 6 | computer_science | 10 | axiom-9 (Turing), math-7 (Graph), method-12 (Parallel) |
| 7 | machine_learning | 10 | method-9 (Data-Driven), method-11 (Dim Reduction) |
| 8 | optimization | 10 | math-3 (Optimization), method-1 (Search), method-3 (DP) |
| 9 | logic | 8 | axiom-3 (LEM), axiom-5 (Gödel), axiom-8 (HoTT) |
| 10 | mechanical_system | 7 | phys-1 (Oscillation), phys-8 (Failure) |
| 11 | thermal_system | 5 | phys-2 (Thermal), meta-5 (Hierarchy) |
| 12 | statistics | 5 | math-4 (Probability), meta-5 (Hierarchy) |
| 13 | quantum_physics | 5 | phys-5 (Noise), phys-7 (Phase Transition) |
| 14 | chemistry | 5 | meta-6 (Epistemic), phys-4 (Material) |
| 15 | electrical_system | 4 | phys-3 (EM), phys-6 (Delay) |
| 16 | economics | 4 | method-6 (Feedback), axiom-12 (Conservation) |
| 17 | parallel_computing | 3 | method-12 (Parallel), axiom-6 (Euclid) |
| 18 | ecology | 3 | meta-4 (Convergence), method-6 (Feedback) |
| 19 | probability_theory | 2 | math-4 (Probability) |
| 20 | linguistics | 2 | axiom-7 (Category Theory) |
| 21 | climate_science | 1 | method-8 (Simulation) |
| 22 | distributed_systems | 1 | method-12 (Parallel) |
| 23 | embedded_systems | 1 | phys-6 (Delay) |
| 24 | epidemiology | 1 | method-8 (Simulation) |
| 25 | image_processing | 1 | method-10 (Spectral) |
| 26 | information_theory | 1 | math-6 (Entropy) |
| 27 | social_science | 1 | meta-2 (Causation) |

---

## Top 10 Domains by Node Coverage

```
control_system      ████████████████████████████ 27
mathematics         ██████████████████████ 22
materials_science   █████████████████ 17
physics             ███████████████ 15
biology             ███████████ 11
computer_science    ██████████ 10
machine_learning    ██████████ 10
optimization        ██████████ 10
logic               ████████ 8
mechanical_system   ███████ 7
```

---

## Domain — L0-L4 Node Mapping (Detailed)

### control_system (27 nodes)

| Node ID | Node Name | Strength | Evidence Keywords |
|---------|-----------|----------|-------------------|
| meta-1 | Double-Loop Learning | 0.9 | control system, controller |
| meta-4 | Convergence & Stability | 0.7 | control system, control |
| meta-6 | Epistemic Boundary | 0.7 | In control, control |
| method-1 | Search & Traversal | 0.7 | control system, control, controller |
| method-3 | Dynamic Programming | 0.7 | control, MPC |
| method-4 | Adaptive Update | 0.9 | control system, adaptive control, LMS |
| method-6 | Feedback & Causal Loop | 0.9 | control, PID, H2/Hinf |
| method-7 | Feedforward | 0.9 | FxLMS, control |
| method-8 | Model-Based Simulation | 0.7 | MPC, control |
| method-10 | Spectral Decomposition | 0.7 | vibration control, tonal harmonic |
| phys-1 | Mechanical Oscillation | 0.7 | vibration, resonance, damping |
| phys-2 | Thermal Transport | 0.5 | machine tools, thermal error |
| phys-3 | Electromagnetic Coupling | 0.5 | piezoelectric, capacitive |
| phys-5 | Signal & Noise | 0.5 | sensor noise, dB |
| phys-6 | Spatiotemporal Delay | 0.7 | phase lag, bandwidth |
| phys-7 | Phase Transition | 0.7 | bifurcation, stable to unstable |
| phys-8 | Structural Stability | 0.7 | structural stability, parameter perturbations |

*(Full list in source JSON; truncated for readability)*

### mathematics (22 nodes)

| Node ID | Node Name | Strength | Evidence Keywords |
|---------|-----------|----------|-------------------|
| axiom-1 | Set Theory & ZFC | 0.7 | mathematics, math |
| axiom-3 | Law of Excluded Middle | 0.7 | mathematics, math |
| axiom-4 | Continuum Hypothesis | 0.5 | math |
| axiom-7 | Category Theory | 0.5 | math |
| math-1 | Function Approximation | 0.7 | mathematics, math |
| math-2 | Dynamical Systems | 0.7 | mathematics, math |
| math-3 | Optimization Theory | 0.7 | mathematics, math, convex |
| math-5 | Spectral Analysis | 0.7 | mathematics, math |
| math-8 | Algebraic Structure | 0.7 | group, algebra, symmetry |

### materials_science (17 nodes)

| Node ID | Node Name | Strength | Evidence Keywords |
|---------|-----------|----------|-------------------|
| meta-6 | Epistemic Boundary | 0.9 | materials, material |
| phys-4 | Material Response | 0.9 | composites, rule of mixtures |
| phys-7 | Phase Transition | 0.7 | materials, glass transition |
| phys-8 | Structural Stability | 0.5 | materials, Weibull |
| math-8 | Algebraic Structure | 0.5 | crystal, symmetry groups |

---

## DialogMesh Integration Interface

```python
# Domain lookup
from lcortex.seeds import DomainRegistry

# Get all nodes for a domain
nodes = DomainRegistry.get_nodes("control_system")
# → [{node_id, node_name, strength, evidence}, ...]

# Get all domains for a node
domains = DomainRegistry.get_domains("method-4")
# → [{domain, strength, evidence}, ...]

# Check if a keyword maps to a domain
match = DomainRegistry.match_keyword("vibration")
# → {"domain": "mechanical_system", "nodes": ["phys-1", ...], "strength": 0.7}
```

---

## Schema (for automated parsing)

```json
{
  "domain_id": "control_system",
  "node_mappings": [
    {
      "node_id": "meta-1",
      "node_name": "Double-Loop Learning",
      "node_level": 0,
      "strength": 0.9,
      "evidence": ["control system", "control", "controller"]
    }
  ],
  "total_nodes": 27,
  "primary_layers": [0, 3, 4]
}
```
