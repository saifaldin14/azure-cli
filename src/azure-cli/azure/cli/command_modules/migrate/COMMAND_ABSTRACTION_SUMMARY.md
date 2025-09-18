# Command Abstraction Layer - Implementation Summary

## Overview
The command abstraction layer provides version-aware PowerShell command construction and intelligent parameter mapping for Azure Migrate CLI commands. This implementation addresses the core issues around PowerShell module version compatibility and parameter mapping failures.

## Key Components Implemented

### 1. EnhancedParameterMapper
**Purpose**: Intelligent parameter mapping with runtime discovery
**Key Features**:
- Version-aware parameter mapping based on PowerShell module versions
- Runtime signature discovery for unknown versions
- Fuzzy parameter matching with transformation patterns
- Confidence-based parameter matching

**Core Methods**:
- `map_parameters()`: Main parameter mapping entry point
- `get_compatibility_status()`: Determines version compatibility
- `_discover_parameters_runtime()`: Runtime parameter discovery
- `_find_parameter_match()`: Intelligent parameter name matching

### 2. Data Classes and Enums

#### CompatibilityStatus
```python
SUPPORTED = "supported"      # Fully tested and supported
COMPATIBLE = "compatible"    # Should work, may have minor issues  
EXPERIMENTAL = "experimental"# Untested, runtime discovery required
UNKNOWN = "unknown"         # No information available
INCOMPATIBLE = "incompatible"# Known breaking changes
```

#### CommandTemplate
```python
@dataclass
class CommandTemplate:
    base_command: str
    parameters: List[CommandParameter]
    description: str = ""
    requires_confirmation: bool = False
    fallback_commands: List[str] = None
```

#### CommandParameter
```python
@dataclass
class CommandParameter:
    name: str
    default_value: Any = None
    required: bool = False
    parameter_type: str = "string"
    description: str = ""
```

### 3. Command Templates
Pre-defined templates for common Azure Migrate operations:
- `get_discovered_server`: Get-AzMigrateDiscoveredServer
- `create_server_replication`: New-AzMigrateServerReplication
- `create_local_server_replication`: New-AzMigrateLocalServerReplication
- `create_local_disk_mapping`: New-AzMigrateLocalDiskMappingObject
- `get_local_job`: Get-AzMigrateLocalJob

### 4. PowerShellCommandBuilder
**Purpose**: Builds PowerShell commands from templates with proper parameter formatting
**Key Features**:
- Template-based command construction
- Automatic parameter validation
- PowerShell-specific parameter formatting
- Support for different parameter types (bool, string, int, float)

### 5. CommandExecutor
**Purpose**: Executes PowerShell commands with fallback mechanisms
**Key Features**:
- Template-based command execution
- Fallback command support
- Error handling and retry logic
- Integration with parameter mapping

### 6. CompatibilityLayer
**Purpose**: Main entry point that combines all components
**Key Features**:
- Unified interface for command execution
- Dynamic module version updates
- Centralized configuration management

## Parameter Mapping Strategy

### Version-Based Mapping
The system maintains a mapping of parameter names across different module versions:

```python
PARAMETER_MAPPINGS = {
    "New-AzMigrateServerReplication": {
        "2.5.0": {
            "MachineId": "SourceMachineId",  # Parameter renamed
            "RequiredParameter": "NewRequiredParam"  # New required parameter
        },
        "2.0.0": {
            "MachineId": "MachineId",
            "TargetResourceGroupId": "TargetResourceGroupId"
        }
    }
}
```

### Runtime Discovery
For unknown versions or when static mappings fail:
1. Query PowerShell command signature using `Get-Command`
2. Extract available parameters and requirements
3. Apply intelligent matching algorithms
4. Use fuzzy matching with confidence scoring

### Parameter Transformation Patterns
Common transformation patterns applied during matching:
- `Id` ↔ `ID`: Case variations
- `VM` ↔ `VirtualMachine`: Abbreviation expansion
- `Target`/`Source` prefix handling
- `Name` ↔ `Id`: Semantic equivalents

## Integration Points

### With _powershell_utils.py
```python
# Enhanced PowerShell executor integration
enhanced_mapper = EnhancedParameterMapper(module_versions, ps_executor)
compatibility_layer = CompatibilityLayer(ps_executor, module_versions)
```

### With custom.py
```python
# Command execution through compatibility layer
compatibility_layer = CompatibilityLayer(ps_executor, module_versions)
result = compatibility_layer.execute_command("create_server_replication", 
                                           MachineId=machine_id,
                                           TargetResourceGroupId=rg_id)
```

### With _version_compatibility.py
```python
# Version information feeding into parameter mapping
version_checker = VersionCompatibilityChecker(ps_executor)
module_versions = version_checker.get_current_versions()
```

## Error Handling Strategy

### Graceful Degradation
1. **Exact Match**: Use known parameter mappings
2. **Runtime Discovery**: Query PowerShell for current signature
3. **Fuzzy Matching**: Apply transformation patterns
4. **Fallback Commands**: Use alternative command formats
5. **Error Reporting**: Provide detailed diagnostic information

### Confidence Scoring
Parameter matches are scored on confidence (0.0 to 1.0):
- 1.0: Exact match
- 0.8: Successful transformation
- 0.5-0.7: Partial/fuzzy match
- <0.5: Rejected as unreliable

## Testing and Validation

### Unit Test Coverage
- Parameter mapping accuracy
- Runtime discovery functionality
- Command template validation
- Fallback mechanism testing
- Integration with PowerShell executor

### Integration Testing
- End-to-end command execution
- Version compatibility scenarios
- Error handling paths
- Performance benchmarking

## Usage Examples

### Basic Parameter Mapping
```python
module_versions = {"Az.Migrate": "2.5.0"}
mapper = EnhancedParameterMapper(module_versions, ps_executor)

original_params = {"MachineId": "test-123", "TargetResourceGroupId": "rg-test"}
mapped_params = mapper.map_parameters("New-AzMigrateServerReplication", original_params)
```

### Command Execution
```python
compatibility_layer = CompatibilityLayer(ps_executor, module_versions)
result = compatibility_layer.execute_command(
    "create_server_replication",
    MachineId="vm-123",
    TargetResourceGroupId="/subscriptions/.../resourceGroups/test-rg",
    TargetNetworkId="/subscriptions/.../virtualNetworks/test-vnet",
    TargetVMName="migrated-vm",
    OSDiskID="disk-123"
)
```

### Version Compatibility Check
```python
status = mapper.get_compatibility_status("New-AzMigrateServerReplication")
if status == CompatibilityStatus.EXPERIMENTAL:
    logger.warning("Command may require runtime parameter discovery")
```

## Performance Considerations

### Caching Strategy
- Command signatures cached by version
- Parameter mappings cached per session
- Lazy loading of runtime discovery

### Optimization Techniques
- Batch parameter validation
- Efficient fuzzy matching algorithms
- Minimal PowerShell round-trips

## Future Enhancements

### Potential Improvements
1. **Machine Learning**: Learn parameter mappings from usage patterns
2. **Telemetry Integration**: Collect success/failure metrics
3. **Auto-Update**: Download updated mappings from service
4. **Schema Validation**: Validate parameter types and constraints
5. **Documentation Generation**: Auto-generate command help

### Extensibility Points
- Custom transformation patterns
- Additional parameter types
- Plugin-based command extensions
- Custom validation rules

## Backward Compatibility

### Legacy Support
The `ParameterMapper` class is maintained for backward compatibility:
```python
# Legacy usage still works
legacy_mapper = ParameterMapper(module_versions)
mapped_params = legacy_mapper.map_parameters(command_name, params)
```

### Migration Path
Existing code can gradually adopt enhanced features:
1. Replace `ParameterMapper` with `EnhancedParameterMapper`
2. Add `powershell_executor` parameter for runtime discovery
3. Use `CompatibilityLayer` for unified command execution
4. Implement fallback commands for critical operations

This implementation provides a robust, extensible foundation for handling PowerShell module version compatibility issues while maintaining backward compatibility with existing Azure Migrate CLI functionality.
