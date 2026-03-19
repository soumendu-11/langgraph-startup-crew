"""
Entry point: Run the multi-turn 3-employee startup conversation
for a satellite imagery company.
"""

from workflow import stream_startup_workflow


SATELLITE_IMAGERY_PITCH = """
I want to build a satellite imagery analytics company. The idea is to use AI to process
satellite images and provide actionable insights for agriculture, urban planning,
and environmental monitoring.

We'd offer an API and dashboard where customers upload coordinates or draw regions
on a map, and we return analyzed imagery with change detection, crop health scores,
deforestation alerts, and urban expansion tracking.

Target customers: agricultural enterprises, government agencies, insurance companies,
and environmental NGOs.

Revenue model: SaaS subscription with tiered pricing based on area coverage and
refresh frequency.
"""


def main():
    print("🚀 STARTUP BUILDER — Satellite Imagery Company")
    print("=" * 70)
    print(f"\n📝 FOUNDER'S PITCH:\n{SATELLITE_IMAGERY_PITCH}")
    print("=" * 70)
    print("\nLaunching 3-turn multi-agent conversation...\n")

    final_plan = ""
    for node_name, output in stream_startup_workflow(SATELLITE_IMAGERY_PITCH):
        if node_name == "router":
            print(f"\n{'='*70}")
            print(f"🔄 Turn complete — moving to next round...")
            print(f"{'='*70}\n")
            continue

        if "messages" in output:
            for msg in output["messages"]:
                content = msg.content if hasattr(msg, "content") else msg.get("content", "")
                print(content)
                print("\n" + "-" * 70 + "\n")

        if "final_plan" in output and output["final_plan"]:
            final_plan = output["final_plan"]

    if final_plan:
        print("\n" + "=" * 70)
        print("✅ CONVERSATION COMPLETE — Action plan generated!")
        print("=" * 70)


if __name__ == "__main__":
    main()
