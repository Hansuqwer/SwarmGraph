from swarm import SwarmConfig, SwarmState, build_swarm_graph

config = SwarmConfig(
    topology="hierarchical",
    consensus_protocol="raft",
    max_agents=5,
    sona_enabled=True,
)

state = SwarmState(
    swarm_id="smoke-001",
    objective="Implement a typed add(a, b) -> int function with tests",
    config=config,
)

graph = build_swarm_graph(config)
result = graph.invoke(
    state.to_json_dict(),
    config={"configurable": {"thread_id": "smoke-thread-1"}},
)
final = SwarmState.from_json_dict(result)

print(f"Status:         {final.status}")
print(f"Final output:   {final.final_output[:200]}")
print(f"Iterations:     {final.iteration}")
print(f"SONA cycles:    {final.sona_cycle_count}")
print(f"Objective hash: {final.objective_hash}")
print(f"History entries: {len(final.history)}")
