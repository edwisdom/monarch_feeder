#!/bin/bash

# Build script for Human Interest Computer Use Automation
set -e

IMAGE_NAME="computer-use-human-interest"
CONTAINER_NAME="human-interest-automation"

echo "🏗️  Building Human Interest Computer Use container..."

# Build the Docker image
docker build -f monarch_feeder/claude_computer_use/human_interest/Dockerfile -t $IMAGE_NAME .

echo "✅ Build completed successfully!"
echo ""
echo "🚀 To run the Human Interest automation:"
echo ""
echo "   1. Copy .env.example to .env and fill in your credentials"
echo "   2. Run: ./run_human_interest.sh"