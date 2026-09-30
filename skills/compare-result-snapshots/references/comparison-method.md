# Before/after comparison heuristics

Always look at both absolute and relative change. A 1000% relative move from 0.001 to 0.011 may be less important than a 5% move on a billion-unit exposure.

When stable keys exist, classify movement as:

- **broad**: many keys move in the same direction;
- **concentrated**: a small number of keys explain much of the total delta;
- **composition**: added/removed keys explain the aggregate;
- **mixed**: offsets hide large underlying movers.

This skill intentionally calculates facts only. Causal interpretation belongs in the investigation layer.
