# Azure Migrate CLI - Enhanced Architecture

This document describes the comprehensive solution implemented to address PowerShell dependency issues and improve reliability of the Azure Migrate CLI module.

## Overview

The Azure Migrate CLI module has been enhanced with a multi-layered architecture that provides:

- **Version compatibility management** for PowerShell modules
- **Enhanced error handling** with intelligent error classification and recovery suggestions
- **Command abstraction layer** for version-agnostic PowerShell command execution
- **Comprehensive pre-flight checks** to prevent runtime failures
- **Graceful degradation** when encountering version compatibility issues

## Architecture Components

### 1. Version Compatibility Layer (`_version_compatibility.py`)

**Purpose**: Manages PowerShell module version compatibility and provides compatibility reporting.

**Key Features**:
- Tracks supported version ranges for all PowerShell modules
- Identifies breaking changes across versions
- Provides detailed compatibility reports
- Suggests appropriate actions for version issues

**Usage**:
```python
from ._version_compatibility import VersionCompatibilityChecker

checker = VersionCompatibilityChecker(powershell_executor)
compatibility_report = checker.check_all_modules()
```

### 2. Error Handling and Diagnostics (`_error_handling.py`)

**Purpose**: Intelligent error classification and comprehensive diagnostic collection.

**Key Features**:
- Categorizes errors into specific types (PowerShell not found, module missing, auth required, etc.)
- Provides context-aware recovery suggestions
- Collects detailed diagnostic information for troubleshooting
- Formats user-friendly error messages

**Error Categories**:
- PowerShell availability issues
- Module installation/version problems  
- Azure authentication issues
- Resource access problems
- Network connectivity issues
- Migration service errors

**Usage**:
```python
from ._error_handling import handle_migrate_error, ErrorCategory

try:
    # Migration operation
    pass
except Exception as e:
    handle_migrate_error(str(e), exception=e, enable_diagnostics=True)
```

### 3. Command Abstraction Layer (`_command_abstraction.py`)

**Purpose**: Provides version-aware PowerShell command construction and execution.

**Key Features**:
- Parameter mapping across different module versions
- Template-based command construction
- Fallback mechanisms for compatibility issues
- Centralized command definitions

**Components**:
- **ParameterMapper**: Maps parameter names across versions
- **PowerShellCommandBuilder**: Constructs commands from templates
- **CommandExecutor**: Executes commands with fallback support
- **CompatibilityLayer**: Main interface combining all components

**Usage**:
```python
compatibility_layer = ps_executor.get_compatibility_layer()
result = compatibility_layer.execute_command(
    'create_server_replication',
    project_name=project_name,
    resource_group_name=resource_group_name,
    # ... other parameters
)
```

### 4. Enhanced PowerShell Executor (`_powershell_utils.py`)

**Purpose**: Extended PowerShell executor with reliability and compatibility features.

**New Methods**:
- `run_preflight_checks()`: Comprehensive environment validation
- `execute_with_error_handling()`: Execute scripts with enhanced error handling
- `get_compatibility_layer()`: Access to the compatibility layer
- `_check_required_modules()`: Module installation verification

## User Experience Improvements

### 1. Enhanced Setup Command

```bash
az migrate setup-env
```

**New Features**:
- Comprehensive environment checking
- Automatic module installation
- Version compatibility verification
- Platform-specific setup guidance
- Detailed progress reporting

### 2. Comprehensive Diagnostics

```bash
az migrate check-prerequisites
```

**Provides**:
- Complete environment diagnostic report
- PowerShell and module status
- Azure authentication verification
- Version compatibility analysis
- Actionable recommendations

### 3. Smart Error Messages

When errors occur, users now receive:
- Clear problem identification
- Specific recovery steps
- Related command suggestions
- Diagnostic information (when enabled)

**Example Error Output**:
```
Azure Migrate Error: Module Az.Migrate not found

Suggested Solutions:
  1. Install required modules: az migrate powershell update-modules
  2. Run: Install-Module Az.Migrate -Force in PowerShell
  3. Check PowerShell execution policy: Get-ExecutionPolicy

Error Category: module_not_installed
```

## Migration Scenario Handling

### Before Running Commands

1. **Environment Setup**:
   ```bash
   az migrate setup-env --install-powershell
   ```

2. **Prerequisites Check**:
   ```bash
   az migrate check-prerequisites
   ```

3. **Authentication**:
   ```bash
   az migrate auth login
   ```

### During Command Execution

The system automatically:
- Runs pre-flight checks
- Attempts compatibility layer execution
- Falls back to direct PowerShell if needed
- Provides detailed error messages with recovery suggestions

### Error Recovery

When issues occur:
1. **Automatic Classification**: Error is categorized and mapped to solutions
2. **Recovery Suggestions**: Specific steps provided based on error type
3. **Diagnostic Collection**: Detailed information gathered for complex issues
4. **Guided Resolution**: Users directed to appropriate commands

## Version Compatibility Management

### Supported Module Versions

| Module | Minimum | Recommended | Maximum | Notes |
|--------|---------|-------------|---------|--------|
| Az.Migrate | 2.0.0 | 2.2.0 | 3.0.0 | Core migration functionality |
| Az.StackHCI | 1.0.0 | 1.4.0 | 2.0.0 | Local migration support |
| Az.Accounts | 2.0.0 | 2.12.0 | 3.0.0 | Authentication |
| Az.Profile | 1.0.0 | 1.2.0 | 2.0.0 | Context management |
| Az.Resources | 4.0.0 | 6.0.0 | 7.0.0 | Resource operations |

### Breaking Changes Tracking

The system tracks known breaking changes:
- Parameter name changes (e.g., `ProjectName` → `MigrateProjectName` in v2.1.0)
- New required parameters 
- Cmdlet signature changes
- Deprecated functionality

## Command Templates

Pre-defined templates handle common operations:

- `get_discovered_server`: Server discovery operations
- `create_server_replication`: Server replication setup  
- `create_local_server_replication`: Local migration replication
- `create_local_disk_mapping`: Disk mapping for local migration
- `get_local_job`: Local migration job status

## Fallback Mechanisms

### Primary → Compatibility Layer → Direct PowerShell

1. **Primary Execution**: Use compatibility layer with version-aware commands
2. **Compatibility Fallback**: If primary fails, try alternative parameter mappings
3. **Direct Fallback**: If all else fails, execute original PowerShell commands
4. **Error Handling**: Provide clear guidance regardless of failure point

## Configuration and Customization

### Module Configuration (`migrate_config.json`)

```json
{
  "powershell_modules": {
    "Az.Migrate": {
      "minimum_version": "2.0.0",
      "recommended_version": "2.2.0", 
      "maximum_version": "3.0.0"
    }
  },
  "compatibility_mode": "auto",
  "pre_flight_checks": true,
  "diagnostic_logging": false
}
```

### Environment Variables

- `MIGRATE_CLI_DIAGNOSTIC_MODE`: Enable detailed diagnostic logging
- `MIGRATE_CLI_COMPATIBILITY_MODE`: Force specific compatibility mode
- `MIGRATE_CLI_SKIP_PREFLIGHT`: Skip pre-flight checks (not recommended)

## Testing and Validation

### Test Framework Enhancements

- Mock PowerShell layer for unit testing
- Version simulation for compatibility testing
- Error injection for error handling validation
- End-to-end scenario testing

### Regression Testing

- Automated compatibility testing across supported versions
- Breaking change detection
- Performance regression monitoring
- User experience validation

## Migration from Legacy Code

### Backwards Compatibility

- Existing commands continue to work unchanged
- New features are opt-in by default
- Legacy error handling preserved as fallback
- Gradual migration path for custom implementations

### Migration Steps

1. **Update Imports**: Add new module imports
2. **Enable Features**: Use enhanced commands gradually
3. **Update Error Handling**: Adopt new error handling patterns
4. **Test Thoroughly**: Validate against target environments

## Best Practices

### For CLI Users

1. **Always run setup first**: `az migrate setup-env`
2. **Check prerequisites**: `az migrate check-prerequisites`
3. **Keep modules updated**: `az migrate powershell update-modules`
4. **Use diagnostic mode for issues**: Add `--enable-diagnostics` to commands

### For Developers

1. **Use compatibility layer**: Prefer template-based commands
2. **Handle errors properly**: Use enhanced error handling functions
3. **Test version compatibility**: Validate against supported version ranges
4. **Provide clear error messages**: Include recovery suggestions

## Future Enhancements

### Planned Features

- **Remote compatibility updates**: Download compatibility data from service
- **Automated module management**: Automatic module updates and rollbacks
- **Advanced diagnostics**: Integration with Azure Monitor for telemetry
- **Multi-tenant support**: Enhanced support for complex Azure environments

### Performance Optimizations

- **Caching layer**: Cache module version information and compatibility data
- **Lazy initialization**: Initialize components only when needed
- **Parallel execution**: Concurrent pre-flight checks and operations
- **Reduced PowerShell overhead**: Minimize PowerShell process creation

## Troubleshooting Guide

### Common Issues and Solutions

**Issue**: PowerShell not found
**Solution**: Run `az migrate setup-env --install-powershell`

**Issue**: Module version incompatible  
**Solution**: Run `az migrate powershell update-modules`

**Issue**: Authentication required
**Solution**: Run `az migrate auth login`

**Issue**: Resource not found
**Solution**: Verify resource names with `az migrate verify-setup`

### Advanced Diagnostics

For complex issues:
1. Enable diagnostic mode: `--enable-diagnostics`
2. Collect environment info: `az migrate check-prerequisites` 
3. Review compatibility report
4. Check Azure service status
5. Contact support with diagnostic output

## Summary

This enhanced architecture provides a robust, user-friendly, and maintainable solution for Azure Migrate CLI operations. The multi-layered approach ensures reliability while maintaining backwards compatibility and providing clear guidance for issue resolution.

The key benefits include:
- **Improved Reliability**: Pre-flight checks prevent runtime failures
- **Better User Experience**: Clear error messages and recovery guidance
- **Future-Proof Design**: Version compatibility management handles PowerShell updates
- **Maintainability**: Modular architecture enables easy updates and testing
- **Comprehensive Diagnostics**: Detailed information for troubleshooting complex issues
