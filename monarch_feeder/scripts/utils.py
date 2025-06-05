from pathlib import Path


def update_env_variable(var_name: str, var_value: str, env_path: str = ".env") -> None:
    """
    Update or add a variable in a .env file.

    Args:
        var_name: Name of the environment variable
        var_value: Value to set for the variable
        env_path: Path to the .env file (defaults to ".env")
    """
    env_file = Path(env_path)

    # Read existing content or start with empty list
    lines = []
    if env_file.exists():
        with open(env_file, "r", encoding="utf-8") as f:
            lines = f.readlines()

    # Look for existing variable and update it
    variable_line = f"{var_name}={var_value}\n"
    variable_updated = False

    for i, line in enumerate(lines):
        # Check if line defines our target variable
        if line.strip() and not line.strip().startswith("#"):
            if line.split("=", 1)[0].strip() == var_name:
                lines[i] = variable_line
                variable_updated = True
                break

    # If variable wasn't found, append it
    if not variable_updated:
        # Ensure file ends with newline before adding new variable
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        lines.append(variable_line)

    # Write updated content back to file
    with open(env_file, "w", encoding="utf-8") as f:
        f.writelines(lines)
