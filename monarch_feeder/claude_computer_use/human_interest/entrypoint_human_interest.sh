#!/bin/bash
set -e

echo "🚀 Starting Human Interest Computer Use Automation..."

# Start the desktop environment
echo "📺 Starting desktop environment..."
./start_all.sh

# Wait a moment for services to start
sleep 3

echo "🔧 Environment setup complete"
echo "📊 Starting Human Interest data extraction..."

# Run the Human Interest automation script
python -m computer_use_demo.example_human_interest

echo "✅ Human Interest automation completed!"
echo "📁 Check the human_interest_outputs/ directory for results"
echo "📸 Check the human_interest_screenshots/ directory for screenshots"

# Keep the container running so you can inspect results
echo "🔍 Container will remain running for result inspection..."
echo "💡 Use 'docker exec -it <container_name> bash' to inspect results"
echo "🛑 Press Ctrl+C to stop the container"

# Keep container alive
tail -f /dev/null 