# Dockerfile for running Human Interest automation script
# Uses the existing computer use demo container as base

FROM ghcr.io/anthropics/anthropic-quickstarts:computer-use-demo-latest

# Switch to root to install additional packages if needed
USER root
RUN pip install python-dotenv==1.1.0 instructor[anthropic]==1.8.3

# Switch back to computeruse user
USER computeruse
WORKDIR /home/computeruse

# Copy our custom entrypoint
COPY --chown=computeruse:computeruse monarch_feeder/claude_computer_use/human_interest/entrypoint_human_interest.sh ./entrypoint_human_interest.sh
RUN chmod +x ./entrypoint_human_interest.sh

# Copy the entire computer_use_demo directory with all local changes
# This ensures local modifications override any installed package
COPY --chown=computeruse:computeruse monarch_feeder/claude_computer_use/computer_use_demo/ ./computer_use_demo/

# Ensure the local computer_use_demo is in Python path and takes precedence
ENV PYTHONPATH="/home/computeruse:${PYTHONPATH}"

# Set default display environment variables (can be overridden by .env file)
ENV WIDTH=1024
ENV HEIGHT=768
ENV DISPLAY_NUM=1

# Create output directories
RUN mkdir -p ./human_interest_outputs ./human_interest_screenshots

# Use our custom entrypoint
ENTRYPOINT ["./entrypoint_human_interest.sh"] 