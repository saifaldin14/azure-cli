# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""
Command abstraction layer for Azure Migrate CLI module.
Provides version-aware PowerShell command construction and parameter mapping.
"""

import re
from enum import Enum
from dataclasses import dataclass
from typing import Dict, List, Optional, Any
from packaging import version
from knack.log import get_logger

logger = get_logger(__name__)

class CompatibilityStatus(Enum):
    """Compatibility status for PowerShell module versions."""
    SUPPORTED = "supported"          # Fully tested and supported
    COMPATIBLE = "compatible"        # Should work, may have minor issues
    EXPERIMENTAL = "experimental"    # Untested, runtime discovery required
    UNKNOWN = "unknown"             # No information available
    INCOMPATIBLE = "incompatible"   # Known to have breaking changes

@dataclass
class CommandSignature:
    """Represents a PowerShell command signature discovered at runtime."""
    command_name: str
    parameters: Dict[str, Dict[str, Any]]  # param_name -> {type, required, etc.}
    module_version: str
    discovery_timestamp: str
    
@dataclass
class ParameterMatch:
    """Result of parameter matching attempt."""
    original_name: str
    matched_name: Optional[str]
    confidence: float  # 0.0 to 1.0
    transformation_applied: Optional[str]

@dataclass
class CommandParameter:
    """Represents a command parameter definition."""
    name: str
    default_value: Any = None
    required: bool = False
    parameter_type: str = "string"
    description: str = ""

@dataclass
class CommandTemplate:
    """Template for building PowerShell commands."""
    base_command: str
    parameters: List[CommandParameter]
    description: str = ""
    requires_confirmation: bool = False
    fallback_commands: List[str] = None
    
    def __post_init__(self):
        if self.fallback_commands is None:
            self.fallback_commands = []
    
class EnhancedParameterMapper:
    """Enhanced parameter mapper with runtime discovery and intelligent matching."""
    
    def __init__(self, module_versions: Dict[str, str], powershell_executor=None):
        """
        Initialize enhanced parameter mapper.
        
        Args:
            module_versions: Dict of module_name -> version_string
            powershell_executor: PowerShell executor for runtime discovery
        """
        self.module_versions = module_versions
        self.ps_executor = powershell_executor
        self._signature_cache = {}
        self._parameter_cache = {}
        
        # Known parameter changes across versions (existing mappings)
        self.PARAMETER_MAPPINGS = {
            "Get-AzMigrateDiscoveredServer": {
                "2.1.0": {
                    "ProjectName": "MigrateProjectName",
                    "ResourceGroupName": "ResourceGroupName"
                },
                "2.0.0": {
                    "ProjectName": "ProjectName",
                    "ResourceGroupName": "ResourceGroupName"
                }
            },
            "New-AzMigrateServerReplication": {
                "2.5.0": {
                    "MachineId": "SourceMachineId",
                    "TargetResourceGroupId": "TargetResourceGroupId",
                    "RequiredParameter": "NewRequiredParam"
                },
                "2.0.0": {
                    "MachineId": "MachineId",
                    "TargetResourceGroupId": "TargetResourceGroupId"
                }
            },
            "New-AzMigrateLocalServerReplication": {
                "1.4.0": {
                    "SourceApplianceName": "SourceAppliance",
                    "TargetApplianceName": "TargetAppliance"
                },
                "1.0.0": {
                    "SourceApplianceName": "SourceApplianceName", 
                    "TargetApplianceName": "TargetApplianceName"
                }
            }
        }
        
        # Common parameter name transformations
        self.PARAMETER_TRANSFORMATIONS = [
            (r'Id$', 'ID'),                    # Id -> ID
            (r'ID$', 'Id'),                    # ID -> Id  
            (r'^VM', 'VirtualMachine'),        # VM -> VirtualMachine
            (r'^VirtualMachine', 'VM'),        # VirtualMachine -> VM
            (r'^Target', ''),                  # Target -> (remove prefix)
            (r'^Source', ''),                  # Source -> (remove prefix)
            (r'^(?!Target)', 'Target'),        # (add Target prefix)
            (r'^(?!Source)', 'Source'),        # (add Source prefix)
            (r'Name$', 'Id'),                  # Name -> Id
            (r'Id$', 'Name'),                  # Id -> Name
        ]
    
    def get_compatibility_status(self, command_name: str) -> CompatibilityStatus:
        """Determine compatibility status for a command based on installed version."""
        current_version = self._get_effective_version(command_name)
        
        if command_name not in self.PARAMETER_MAPPINGS:
            return CompatibilityStatus.UNKNOWN
            
        mappings = self.PARAMETER_MAPPINGS[command_name]
        highest_mapped_version = max(mappings.keys(), key=lambda v: version.parse(v))
        
        current_ver = version.parse(current_version)
        highest_mapped_ver = version.parse(highest_mapped_version)
        
        if current_ver == highest_mapped_ver:
            return CompatibilityStatus.SUPPORTED
        elif current_ver < highest_mapped_ver:
            return CompatibilityStatus.COMPATIBLE
        elif current_ver > highest_mapped_ver:
            # Version gap - need runtime discovery
            return CompatibilityStatus.EXPERIMENTAL
        else:
            return CompatibilityStatus.UNKNOWN
    
    def map_parameters(self, command_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enhanced parameter mapping with runtime discovery and validation.
        
        Args:
            command_name: Name of the PowerShell command
            parameters: Original parameter dictionary
            
        Returns:
            Dict with mapped parameter names
        """
        # Check compatibility status first
        compatibility = self.get_compatibility_status(command_name)
        
        if compatibility == CompatibilityStatus.EXPERIMENTAL:
            logger.warning(f"Command {command_name} version exceeds known mappings, attempting runtime discovery")
            return self._discover_parameters_runtime(command_name, parameters)
        
        # Use existing mapping logic for known versions
        return self._apply_known_mapping(command_name, parameters)
    
    def _apply_known_mapping(self, command_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Apply known parameter mappings based on version."""
        if command_name not in self.PARAMETER_MAPPINGS:
            return parameters
            
        # Get the appropriate version mapping
        mappings = self.PARAMETER_MAPPINGS[command_name]
        current_version = self._get_effective_version(command_name)
        
        # Find the best matching version mapping
        best_mapping = None
        best_version = None
        
        for mapping_version, mapping in mappings.items():
            if version.parse(current_version) >= version.parse(mapping_version):
                if best_version is None or version.parse(mapping_version) > version.parse(best_version):
                    best_mapping = mapping
                    best_version = mapping_version
                    
        if best_mapping is None:
            logger.warning(f"No parameter mapping found for {command_name} version {current_version}")
            return parameters
        
        # Validate that the mapped parameters actually exist
        mapped_parameters = {}
        for original_name, value in parameters.items():
            mapped_name = best_mapping.get(original_name, original_name)
            mapped_parameters[mapped_name] = value
            
            if mapped_name != original_name:
                logger.debug(f"Mapped parameter {original_name} -> {mapped_name} for {command_name}")
        
        # Validate parameters exist if we have PowerShell executor
        if self.ps_executor and not self._validate_parameters_exist(command_name, mapped_parameters):
            logger.warning(f"Mapped parameters invalid for {command_name}, falling back to runtime discovery")
            return self._discover_parameters_runtime(command_name, parameters)
                
        return mapped_parameters
    
    def _validate_parameters_exist(self, command_name: str, parameters: Dict[str, Any]) -> bool:
        """Validate that mapped parameters actually exist in the current PowerShell command."""
        try:
            signature = self._get_command_signature(command_name)
            available_params = [p.lower() for p in signature.get('parameters', [])]
            
            # Check if all our mapped parameters exist (case-insensitive)
            for param_name in parameters.keys():
                if param_name.lower() not in available_params:
                    logger.debug(f"Parameter '{param_name}' not found in {command_name} signature")
                    return False
                    
            return True
        except Exception as e:
            logger.debug(f"Could not validate parameters for {command_name}: {e}")
            return True  # Assume valid if we can't check
    
    def _get_command_signature(self, command_name: str) -> Dict[str, Any]:
        """Get PowerShell command signature via runtime inspection."""
        cache_key = f"{command_name}_{self._get_effective_version(command_name)}"
        
        if cache_key in self._signature_cache:
            return self._signature_cache[cache_key]
            
        if not self.ps_executor:
            return {}
            
        signature_script = f"""
        try {{
            $cmd = Get-Command {command_name} -ErrorAction SilentlyContinue
            if ($cmd -and $cmd.Parameters) {{
                $params = $cmd.Parameters.Keys | ForEach-Object {{ $_ }}
                $required = $cmd.Parameters.Values | Where-Object {{ $_.Attributes.Mandatory -eq $true }} | ForEach-Object {{ $_.Name }}
                $moduleInfo = Get-Module -Name ($cmd.ModuleName) | Select-Object -First 1
                
                $result = @{{
                    'parameters' = $params
                    'required' = $required
                    'module_version' = if ($moduleInfo) {{ $moduleInfo.Version.ToString() }} else {{ 'unknown' }}
                    'command_exists' = $true
                }}
                
                return $result | ConvertTo-Json -Depth 3
            }} else {{
                return @{{ 'command_exists' = $false }} | ConvertTo-Json
            }}
        }} catch {{
            return @{{ 'error' = $_.Exception.Message; 'command_exists' = $false }} | ConvertTo-Json
        }}
        """
        
        try:
            result = self.ps_executor.execute_script_and_return_json(signature_script)
            signature = result.get('result', {})
            
            if signature.get('command_exists', False):
                self._signature_cache[cache_key] = signature
                return signature
            else:
                logger.debug(f"Command {command_name} not found or error occurred")
                return {}
                
        except Exception as e:
            logger.debug(f"Failed to get signature for {command_name}: {e}")
            return {}
    
    def _discover_parameters_runtime(self, command_name: str, original_parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Attempt to map parameters by discovering the actual command signature."""
        signature = self._get_command_signature(command_name)
        available_params = signature.get('parameters', [])
        
        if not available_params:
            logger.warning(f"Could not discover parameters for {command_name}, using original parameters")
            return original_parameters
        
        # Try intelligent parameter name matching
        mapped_params = {}
        unmapped_params = []
        
        for orig_name, value in original_parameters.items():
            match_result = self._find_parameter_match(orig_name, available_params)
            
            if match_result.matched_name:
                mapped_params[match_result.matched_name] = value
                if match_result.matched_name != orig_name:
                    logger.info(f"Runtime mapping: {orig_name} -> {match_result.matched_name} (confidence: {match_result.confidence:.2f})")
                    if match_result.transformation_applied:
                        logger.debug(f"Transformation applied: {match_result.transformation_applied}")
            else:
                unmapped_params.append(orig_name)
                logger.warning(f"Could not map parameter '{orig_name}' for {command_name}")
        
        if unmapped_params:
            logger.warning(f"Unmapped parameters for {command_name}: {unmapped_params}")
            logger.info(f"Available parameters: {available_params}")
                
        return mapped_params
    
    def _find_parameter_match(self, original_name: str, available_params: List[str]) -> ParameterMatch:
        """Find the best matching parameter name using fuzzy matching."""
        # Exact match first (case-insensitive)
        for param in available_params:
            if original_name.lower() == param.lower():
                return ParameterMatch(
                    original_name=original_name,
                    matched_name=param,
                    confidence=1.0,
                    transformation_applied=None
                )
        
        # Try transformations
        best_match = ParameterMatch(
            original_name=original_name,
            matched_name=None,
            confidence=0.0,
            transformation_applied=None
        )
        
        for pattern, replacement in self.PARAMETER_TRANSFORMATIONS:
            if re.search(pattern, original_name):
                transformed = re.sub(pattern, replacement, original_name)
                
                for param in available_params:
                    if transformed.lower() == param.lower():
                        return ParameterMatch(
                            original_name=original_name,
                            matched_name=param,
                            confidence=0.8,
                            transformation_applied=f"{pattern} -> {replacement}"
                        )
        
        # Partial/fuzzy matching
        for param in available_params:
            # Check if either name contains the other
            if (original_name.lower() in param.lower() or 
                param.lower() in original_name.lower()):
                confidence = min(len(original_name), len(param)) / max(len(original_name), len(param))
                
                if confidence > best_match.confidence:
                    best_match = ParameterMatch(
                        original_name=original_name,
                        matched_name=param,
                        confidence=confidence,
                        transformation_applied="partial_match"
                    )
        
        # Only return matches with reasonable confidence
        if best_match.confidence >= 0.5:
            return best_match
        else:
            return ParameterMatch(
                original_name=original_name,
                matched_name=None,
                confidence=0.0,
                transformation_applied=None
            )
    
    def _get_effective_version(self, command_name: str) -> str:
        """Get the effective module version for a command."""
        # Map command to module
        command_to_module = {
            "Get-AzMigrateDiscoveredServer": "Az.Migrate",
            "New-AzMigrateServerReplication": "Az.Migrate", 
            "New-AzMigrateLocalServerReplication": "Az.StackHCI",
            "Get-AzMigrateLocalJob": "Az.StackHCI"
        }
        
        module_name = command_to_module.get(command_name, "Az.Migrate")
        return self.module_versions.get(module_name, "2.0.0")  # Default fallback


# Legacy ParameterMapper for backward compatibility
class ParameterMapper(EnhancedParameterMapper):
    """Legacy parameter mapper - delegates to EnhancedParameterMapper."""
    
    def __init__(self, module_versions: Dict[str, str]):
        super().__init__(module_versions, None)
    
    def map_parameters(self, command_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Legacy interface - uses known mappings only."""
        return self._apply_known_mapping(command_name, parameters)

class PowerShellCommandBuilder:
    """Builds PowerShell commands with version compatibility."""
    
    def __init__(self, parameter_mapper: ParameterMapper):
        self.parameter_mapper = parameter_mapper
        
    def build_command(self, template: CommandTemplate, **kwargs) -> str:
        """
        Build a PowerShell command from a template.
        
        Args:
            template: Command template
            **kwargs: Parameter values
            
        Returns:
            PowerShell command string
        """
        # Prepare parameters
        parameters = {}
        for param in template.parameters:
            if param.name in kwargs:
                parameters[param.name] = kwargs[param.name]
            elif param.required:
                raise ValueError(f"Required parameter '{param.name}' not provided")
                
        # Apply parameter mapping
        mapped_parameters = self.parameter_mapper.map_parameters(template.base_command, parameters)
        
        # Build command string
        command_parts = [template.base_command]
        
        for param_name, param_value in mapped_parameters.items():
            if param_value is not None:
                formatted_param = self._format_parameter(param_name, param_value)
                command_parts.append(formatted_param)
                
        return " `\n    ".join(command_parts)
    
    def _format_parameter(self, name: str, value: Any) -> str:
        """Format a parameter for PowerShell."""
        if isinstance(value, bool):
            if value:
                return f"-{name}"
            else:
                return f"-{name}:$false"
        elif isinstance(value, str):
            # Escape quotes in string values
            escaped_value = value.replace('"', '""')
            return f'-{name} "{escaped_value}"'
        elif isinstance(value, (int, float)):
            return f"-{name} {value}"
        else:
            # Treat as string for now
            return f'-{name} "{str(value)}"'

# Pre-defined command templates
COMMAND_TEMPLATES = {
    "get_discovered_server": CommandTemplate(
        base_command="Get-AzMigrateDiscoveredServer",
        parameters=[
            CommandParameter("ProjectName", None, required=True),
            CommandParameter("ResourceGroupName", None, required=True),
            CommandParameter("SourceMachineType", "VMware"),
            CommandParameter("ServerId", None),
        ]
    ),
    
    "create_server_replication": CommandTemplate(
        base_command="New-AzMigrateServerReplication",
        parameters=[
            CommandParameter("MachineId", None, required=True),
            CommandParameter("TargetResourceGroupId", None, required=True),
            CommandParameter("TargetNetworkId", None, required=True),
            CommandParameter("TargetVMName", None, required=True),
            CommandParameter("OSDiskID", None, required=True),
            CommandParameter("LicenseType", "NoLicenseType"),
            CommandParameter("DiskType", "Standard_LRS"),
            CommandParameter("TargetSubnetName", "default"),
        ]
    ),
    
    "create_local_server_replication": CommandTemplate(
        base_command="New-AzMigrateLocalServerReplication",
        parameters=[
            CommandParameter("MachineId", None, required=True),
            CommandParameter("OSDiskID", None, required=True),
            CommandParameter("TargetStoragePathId", None, required=True),
            CommandParameter("TargetVirtualSwitchId", None, required=True),
            CommandParameter("TargetResourceGroupId", None, required=True),
            CommandParameter("TargetVMName", None, required=True),
            CommandParameter("SourceApplianceName", None, required=True),
            CommandParameter("TargetApplianceName", None, required=True),
        ]
    ),
    
    "create_local_disk_mapping": CommandTemplate(
        base_command="New-AzMigrateLocalDiskMappingObject",
        parameters=[
            CommandParameter("DiskID", None, required=True),
            CommandParameter("IsOSDisk", True, parameter_type="bool"),
            CommandParameter("IsDynamic", False, parameter_type="bool"), 
            CommandParameter("Size", 64, parameter_type="int"),
            CommandParameter("Format", "VHD"),
            CommandParameter("PhysicalSectorSize", 512, parameter_type="int"),
        ]
    ),
    
    "get_local_job": CommandTemplate(
        base_command="Get-AzMigrateLocalJob",
        parameters=[
            CommandParameter("ResourceGroupName", None, required=True),
            CommandParameter("ProjectName", None, required=True),
            CommandParameter("JobId", None),
            CommandParameter("Name", None),
        ]
    )
}

class CommandExecutor:
    """Executes PowerShell commands with fallback mechanisms."""
    
    def __init__(self, powershell_executor, parameter_mapper: ParameterMapper):
        self.ps_executor = powershell_executor
        self.command_builder = PowerShellCommandBuilder(parameter_mapper)
        
    def execute_template_command(self, template_name: str, fallback_enabled: bool = True, **kwargs) -> Any:
        """
        Execute a command using a predefined template.
        
        Args:
            template_name: Name of the command template
            fallback_enabled: Whether to try fallback approaches
            **kwargs: Command parameters
            
        Returns:
            Command execution result
        """
        if template_name not in COMMAND_TEMPLATES:
            raise ValueError(f"Unknown command template: {template_name}")
            
        template = COMMAND_TEMPLATES[template_name]
        
        try:
            # Build and execute primary command
            command = self.command_builder.build_command(template, **kwargs)
            logger.debug(f"Executing PowerShell command: {command}")
            
            return self.ps_executor.execute_script_interactive(command)
            
        except Exception as e:
            if fallback_enabled and template.fallback_commands:
                logger.warning(f"Primary command failed, trying fallbacks: {e}")
                return self._try_fallback_commands(template.fallback_commands, **kwargs)
            else:
                raise
                
    def _try_fallback_commands(self, fallback_commands: List[str], **kwargs) -> Any:
        """Try fallback commands in order."""
        last_error = None
        
        for fallback_command in fallback_commands:
            try:
                # Simple string substitution for fallback commands
                formatted_command = fallback_command.format(**kwargs)
                logger.debug(f"Trying fallback command: {formatted_command}")
                
                return self.ps_executor.execute_script_interactive(formatted_command)
                
            except Exception as e:
                last_error = e
                logger.debug(f"Fallback command failed: {e}")
                continue
                
        # All fallbacks failed
        raise last_error or Exception("All fallback commands failed")

class CompatibilityLayer:
    """Main compatibility layer that combines all components."""
    
    def __init__(self, powershell_executor, module_versions: Dict[str, str]):
        """
        Initialize the compatibility layer.
        
        Args:
            powershell_executor: PowerShell executor instance
            module_versions: Current module versions
        """
        self.ps_executor = powershell_executor
        self.parameter_mapper = ParameterMapper(module_versions)
        self.command_executor = CommandExecutor(powershell_executor, self.parameter_mapper)
        
    def execute_command(self, template_name: str, **kwargs) -> Any:
        """Execute a command through the compatibility layer."""
        return self.command_executor.execute_template_command(template_name, **kwargs)
        
    def update_module_versions(self, new_versions: Dict[str, str]):
        """Update module versions and reinitialize mappers."""
        self.parameter_mapper = ParameterMapper(new_versions)
        self.command_executor = CommandExecutor(self.ps_executor, self.parameter_mapper)
