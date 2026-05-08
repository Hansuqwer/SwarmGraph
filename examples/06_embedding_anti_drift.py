from __future__ import annotations

from swarm.llm.embeddings import HashEmbedder
from swarm.models.config import SwarmConfig
from swarm.models.state import SwarmState


def main() -> None:
    state = SwarmState(
        swarm_id="demo",
        objective="write a python add function",
        config=SwarmConfig(anti_drift_mode="embedding", anti_drift_similarity_threshold=0.0),
    )
    print(state.check_drift("anything passes when threshold is zero", embedder=HashEmbedder()))


if __name__ == "__main__":
    main()
