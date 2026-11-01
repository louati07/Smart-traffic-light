#!/bin/bash
# Kill Switch & Heartbeat Loss Demonstration
# Contract: PLAN.md Section 8 P6 & Section 14 Step 4

echo "=========================================================="
echo "    KILL SWITCH & HEARTBEAT LOSS SAFETY DEMONSTRATION     "
echo "=========================================================="
echo ""
echo "Running the local FSM heartbeat-loss demonstration (no live API is stopped)..."
echo "After 10 seconds of missing heartbeat, the simulated controller must:"
echo "1. Drop any active priority hold."
echo "2. Revert safely to FALLBACK mode."
echo "3. Continue cycling normal green/yellow/all-red without conflicts."
echo ""
python scripts/kill_switch_demo.py
