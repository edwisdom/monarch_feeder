# Dockerfile for computer use automation
# Uses the existing computer use demo container as base

FROM ghcr.io/anthropics/anthropic-quickstarts:computer-use-demo-latest

# Switch to root to install additional packages if needed
USER root
RUN pip install python-dotenv==1.1.0 instructor[anthropic]==1.8.3 oathtool==2.4.0

# Switch back to computeruse user
USER computeruse
WORKDIR /home/computeruse

# Copy the entire computer_use_demo directory with all local changes
# This ensures local modifications override any installed package
COPY --chown=computeruse:computeruse monarch_feeder/computer_use_demo/ ./computer_use_demo/

# Copy .env file if it exists (for environment variables like MFA secrets)  
COPY --chown=computeruse:computeruse .env* ./

# Copy the generic entrypoint script
COPY --chown=computeruse:computeruse monarch_feeder/computer_use_demo/entrypoint_generic.sh ./entrypoint_generic.sh
RUN chmod +x ./entrypoint_generic.sh

# Ensure the local computer_use_demo is in Python path and takes precedence
ENV PYTHONPATH="/home/computeruse:${PYTHONPATH}"

# Set default display environment variables (can be overridden by .env file)
ENV WIDTH=1024
ENV HEIGHT=768
ENV DISPLAY_NUM=1

# Set default automation list (can be overridden)
ENV AUTOMATION_LIST=human_interest

# Use the entrypoint script which properly starts services and runs the orchestrator
ENTRYPOINT ["./entrypoint_generic.sh"] 