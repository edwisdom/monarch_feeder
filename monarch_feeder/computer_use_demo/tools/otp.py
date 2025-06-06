import os
from typing import Any, Literal

from .base import BaseAnthropicTool, ToolResult


class OTPTool20250124(BaseAnthropicTool):
    """
    A tool that allows the agent to generate OTP (One-Time Password) codes.
    Uses oathtool to generate TOTP codes from environment variables.
    """

    name: Literal["generate_otp"] = "generate_otp"

    def to_params(self) -> Any:
        return {
            "name": self.name,
            "description": "Generate a one-time password (OTP) for multi-factor authentication using a configured secret key.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "service": {
                        "type": "string",
                        "description": "The service name to generate OTP for (e.g., 'rippling', 'human_interest'). This determines which environment variable to use for the secret.",
                    }
                },
                "required": ["service"],
            },
        }

    async def __call__(self, service: str, **kwargs) -> ToolResult:
        """Generate an OTP for the specified service."""
        try:
            # Import oathtool - this might not be available in all environments
            try:
                import oathtool
            except ImportError:
                return ToolResult(
                    error="oathtool library not found. Please install it with: pip install oathtool"
                )

            # Map service names to environment variable names
            service_env_map = {
                "rippling": "RIPPLING_MFA_SECRET",
                "human_interest": "HUMAN_INTEREST_MFA_SECRET",
            }

            # Get the environment variable name for the service
            env_var_name = service_env_map.get(service.lower())
            if not env_var_name:
                available_services = ", ".join(service_env_map.keys())
                return ToolResult(
                    error=f"Unknown service '{service}'. Available services: {available_services}"
                )

            # Get the secret from environment variables
            secret = os.getenv(env_var_name)
            if not secret:
                return ToolResult(
                    error=f"Secret not found in environment variable '{env_var_name}'. Please set it in your environment."
                )

            # Generate the OTP
            otp_code = oathtool.generate_otp(secret)

            return ToolResult(
                output=f"Generated OTP for {service}: {otp_code}",
                system=f"OTP code: {otp_code}",
            )

        except Exception as e:
            return ToolResult(error=f"Failed to generate OTP: {str(e)}")


# For backward compatibility, create alias for older versions
class OTPTool20241022(OTPTool20250124):
    pass
