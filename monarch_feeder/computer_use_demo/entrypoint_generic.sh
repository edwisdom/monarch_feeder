#!/bin/bash
set -e

echo "🚀 Starting Computer Use Automation Orchestrator..."

# Start the desktop environment
echo "📺 Starting desktop environment..."
./start_all.sh

# Wait a moment for services to start
sleep 3

echo "🔧 Environment setup complete"

# Determine which automations to run
# Can be set via environment variable or command line arguments
if [ $# -gt 0 ]; then
    AUTOMATION_ARGS="$*"
    echo "📊 Using automation list from command line: $AUTOMATION_ARGS"
elif [ -n "$AUTOMATION_LIST" ]; then
    AUTOMATION_ARGS="$AUTOMATION_LIST"
    echo "📊 Using automation list from environment: $AUTOMATION_ARGS"
else
    AUTOMATION_ARGS="human_interest"
    echo "📊 Using default automation: $AUTOMATION_ARGS"
fi

echo "🎯 Running automations: $AUTOMATION_ARGS"

# Run the automation orchestrator
python -m computer_use_demo.automation_orchestrator $AUTOMATION_ARGS

echo "✅ All automations completed!"
echo "📁 Check the automation_outputs/ directory for results"
echo "📸 Check the automation_screenshots/ directory for screenshots"

# Check if container should auto-exit
if [ "$AUTO_EXIT" = "true" ]; then
    echo "🏁 AUTO_EXIT=true, container will now exit"
    echo "💡 To inspect results, run with AUTO_EXIT=false or mount output volumes"
    exit 0
else
    # Keep the container running so you can inspect results
    echo "🔍 Container will remain running for result inspection..."
    echo "💡 Use 'docker exec -it <container_name> bash' to inspect results"
    echo "🛑 Press Ctrl+C to stop the container"
    echo "🏃 To auto-exit after completion, set AUTO_EXIT=true"

    # Keep container alive
    tail -f /dev/null 
fi 