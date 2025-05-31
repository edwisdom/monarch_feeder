#!/bin/bash

# Simple run script for Human Interest Computer Use Automation
set -e

IMAGE_NAME="computer-use-human-interest"
CONTAINER_NAME="human-interest-automation"

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "❌ Error: .env file not found!"
    echo "📝 Please create a .env file with your credentials."
    echo "💡 You can copy env.example to .env and fill in your values:"
    echo "   cp env.example .env"
    exit 1
fi

# Check if image exists
if ! docker image inspect $IMAGE_NAME >/dev/null 2>&1; then
    echo "🏗️  Image not found. Building $IMAGE_NAME..."
    ./build_human_interest.sh
fi

# Create output directories if they don't exist
mkdir -p human_interest_outputs human_interest_screenshots

# Stop and remove any existing container with the same name
if docker ps -a --format "table {{.Names}}" | grep -q "^$CONTAINER_NAME$"; then
    echo "🔄 Stopping and removing existing container: $CONTAINER_NAME"
    docker stop $CONTAINER_NAME >/dev/null 2>&1 || true
    docker rm $CONTAINER_NAME >/dev/null 2>&1 || true
fi

echo "🚀 Running Human Interest automation..."
echo "📊 This will extract your transaction and portfolio data"
echo "⏱️  This may take several minutes to complete"
echo ""

# Run the container
docker run --rm --name $CONTAINER_NAME \
    --env-file .env \
    -v $(pwd)/human_interest_outputs:/home/computeruse/human_interest_outputs \
    -v $(pwd)/human_interest_screenshots:/home/computeruse/human_interest_screenshots \
    $IMAGE_NAME

echo ""
echo "✅ Automation completed!"
echo "📁 Results saved to:"
echo "   - human_interest_outputs/ (JSON data files)"
echo "   - human_interest_screenshots/ (screenshots)" 