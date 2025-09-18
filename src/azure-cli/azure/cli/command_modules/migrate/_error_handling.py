# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""
Error handling and diagnostics for Azure Migrate CLI module.
Provides error classification, recovery suggestions, and diagnostic tools.
"""

import re
import traceback
from enum import Enum
from knack.log import get_logger
from knack.util import CLIError

logger = get_logger(__name__)

class ErrorCategory(Enum):
    """Categories of errors that can occur in Azure Migrate operations."""
    POWERSHELL_NOT_FOUND = "powershell_not_found"
    MODULE_NOT_INSTALLED = "module_not_installed"
    MODULE_VERSION_INCOMPATIBLE = "module_version_incompatible"
    AZURE_AUTH_REQUIRED = "azure_auth_required"
    AZURE_AUTH_EXPIRED = "azure_auth_expired"
    RESOURCE_NOT_FOUND = "resource_not_found"
    PERMISSION_DENIED = "permission_denied"
    NETWORK_ERROR = "network_error"
    CMDLET_NOT_FOUND = "cmdlet_not_found"
    PARAMETER_ERROR = "parameter_error"
    MIGRATION_SERVICE_ERROR = "migration_service_error"
    UNKNOWN_ERROR = "unknown_error"

class ErrorClassifier:
    """Classifies errors and provides recovery suggestions."""
    
    # Error patterns and their classifications
    ERROR_PATTERNS = {
        ErrorCategory.POWERSHELL_NOT_FOUND: [
            r"powershell.*not found",
            r"powershell.*not recognized",
            r"executable.*powershell.*not found"
        ],
        ErrorCategory.MODULE_NOT_INSTALLED: [
            r"module.*not found",
            r"could not load module",
            r"no module named",
            r"install-module.*required"
        ],
        ErrorCategory.MODULE_VERSION_INCOMPATIBLE: [
            r"version.*not supported",
            r"breaking change",
            r"parameter.*not recognized",
            r"cmdlet.*signature.*changed"
        ],
        ErrorCategory.AZURE_AUTH_REQUIRED: [
            r"authentication.*required",
            r"not.*authenticated",
            r"login.*required",
            r"connect-azaccount.*required"
        ],
        ErrorCategory.AZURE_AUTH_EXPIRED: [
            r"authentication.*expired",
            r"token.*expired",
            r"session.*expired",
            r"reauthentication.*required"
        ],
        ErrorCategory.RESOURCE_NOT_FOUND: [
            r"resource.*not found",
            r"subscription.*not found",
            r"resource group.*not found",
            r"project.*not found",
            r"server.*not found"
        ],
        ErrorCategory.PERMISSION_DENIED: [
            r"access.*denied",
            r"permission.*denied",
            r"unauthorized",
            r"forbidden",
            r"insufficient.*permissions"
        ],
        ErrorCategory.NETWORK_ERROR: [
            r"network.*error",
            r"connection.*failed",
            r"timeout",
            r"dns.*resolution.*failed",
            r"unable to connect"
        ],
        ErrorCategory.CMDLET_NOT_FOUND: [
            r"cmdlet.*not recognized",
            r"command.*not found",
            r"get-azmigratediscoveredserver.*not recognized",
            r"new-azmigrateserverreplication.*not recognized"
        ],
        ErrorCategory.PARAMETER_ERROR: [
            r"parameter.*not valid",
            r"invalid.*parameter",
            r"parameter.*missing",
            r"parameter.*required"
        ],
        ErrorCategory.MIGRATION_SERVICE_ERROR: [
            r"migration.*service.*error",
            r"azure migrate.*error",
            r"replication.*failed",
            r"discovery.*failed"
        ]
    }
    
    # Recovery suggestions for each error category
    RECOVERY_SUGGESTIONS = {
        ErrorCategory.POWERSHELL_NOT_FOUND: [
            "Install PowerShell Core from https://github.com/PowerShell/PowerShell",
            "Run: az migrate setup-env --install-powershell",
            "Verify PowerShell is in your system PATH"
        ],
        ErrorCategory.MODULE_NOT_INSTALLED: [
            "Install required modules: az migrate powershell update-modules",
            "Run: Install-Module Az.Migrate -Force in PowerShell",
            "Check PowerShell execution policy: Get-ExecutionPolicy"
        ],
        ErrorCategory.MODULE_VERSION_INCOMPATIBLE: [
            "Update to compatible module version: az migrate powershell update-modules",
            "Check version compatibility: az migrate powershell check-module",
            "Consider downgrading to tested version if issues persist"
        ],
        ErrorCategory.AZURE_AUTH_REQUIRED: [
            "Authenticate to Azure: az migrate auth login",
            "Use device code flow: az migrate auth login --device-code",
            "Set up service principal authentication if needed"
        ],
        ErrorCategory.AZURE_AUTH_EXPIRED: [
            "Re-authenticate to Azure: az migrate auth login",
            "Check current authentication: az migrate auth check",
            "Clear cached credentials if needed"
        ],
        ErrorCategory.RESOURCE_NOT_FOUND: [
            "Verify resource group and project names are correct",
            "Check you have access to the subscription",
            "Run: az migrate verify-setup to validate configuration"
        ],
        ErrorCategory.PERMISSION_DENIED: [
            "Verify you have Contributor role on the resource group",
            "Check Azure Migrate project permissions",
            "Contact your Azure administrator for proper access"
        ],
        ErrorCategory.NETWORK_ERROR: [
            "Check internet connectivity",
            "Verify firewall settings allow Azure connections",
            "Try again after a few minutes"
        ],
        ErrorCategory.CMDLET_NOT_FOUND: [
            "Update PowerShell modules: az migrate powershell update-modules",
            "Import module manually: Import-Module Az.Migrate",
            "Reinstall modules if corruption suspected"
        ],
        ErrorCategory.PARAMETER_ERROR: [
            "Check command syntax and parameter names",
            "Verify all required parameters are provided",
            "Check parameter value formats and types"
        ],
        ErrorCategory.MIGRATION_SERVICE_ERROR: [
            "Check Azure Migrate service status",
            "Verify discovery appliance is running",
            "Review Azure Migrate project configuration"
        ],
        ErrorCategory.UNKNOWN_ERROR: [
            "Enable diagnostic logging for more details",
            "Run: az migrate verify-setup for comprehensive checks",
            "Contact support with full error details"
        ]
    }
    
    @classmethod
    def classify_error(cls, error_message, exception=None):
        """
        Classify an error based on its message and exception.
        
        Args:
            error_message: The error message string
            exception: The original exception object (optional)
            
        Returns:
            ErrorCategory: The classified error category
        """
        error_text = str(error_message).lower()
        
        for category, patterns in cls.ERROR_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, error_text, re.IGNORECASE):
                    return category
                    
        return ErrorCategory.UNKNOWN_ERROR
    
    @classmethod
    def get_recovery_suggestions(cls, error_category):
        """Get recovery suggestions for an error category."""
        return cls.RECOVERY_SUGGESTIONS.get(error_category, cls.RECOVERY_SUGGESTIONS[ErrorCategory.UNKNOWN_ERROR])
    
    @classmethod
    def create_diagnostic_info(cls, error_message, exception=None, context=None):
        """
        Create comprehensive diagnostic information for an error.
        
        Args:
            error_message: The error message
            exception: The original exception (optional)
            context: Additional context information (optional)
            
        Returns:
            dict: Diagnostic information
        """
        category = cls.classify_error(error_message, exception)
        
        diagnostic_info = {
            'error_category': category.value,
            'error_message': str(error_message),
            'recovery_suggestions': cls.get_recovery_suggestions(category),
            'context': context or {},
            'timestamp': None,  # Will be set by caller
            'trace': None
        }
        
        if exception:
            diagnostic_info['exception_type'] = type(exception).__name__
            diagnostic_info['trace'] = traceback.format_exc()
            
        return diagnostic_info

class DiagnosticCollector:
    """Collects diagnostic information for troubleshooting."""
    
    def __init__(self, powershell_executor=None):
        self.ps_executor = powershell_executor
        
    def collect_environment_info(self):
        """Collect comprehensive environment diagnostic information."""
        info = {
            'powershell_info': self._get_powershell_info(),
            'module_info': self._get_module_info(),
            'azure_context': self._get_azure_context(),
            'system_info': self._get_system_info()
        }
        
        return info
    
    def _get_powershell_info(self):
        """Get PowerShell version and availability information."""
        if not self.ps_executor:
            return {'status': 'executor_not_available'}
            
        try:
            ps_info_script = """
            return @{
                'Version' = $PSVersionTable.PSVersion.ToString()
                'Edition' = $PSVersionTable.PSEdition
                'Platform' = $PSVersionTable.Platform
                'ExecutionPolicy' = (Get-ExecutionPolicy).ToString()
                'Available' = $true
            }
            """
            
            result = self.ps_executor.execute_script_and_return_json(ps_info_script)
            return result.get('result', {'status': 'failed_to_get_info'})
            
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e)
            }
    
    def _get_module_info(self):
        """Get information about installed PowerShell modules."""
        if not self.ps_executor:
            return {'status': 'executor_not_available'}
            
        try:
            module_info_script = """
            $modules = @{}
            $moduleNames = @('Az.Migrate', 'Az.StackHCI', 'Az.Accounts', 'Az.Profile', 'Az.Resources')
            
            foreach ($moduleName in $moduleNames) {
                try {
                    $installed = Get-InstalledModule -Name $moduleName -ErrorAction SilentlyContinue
                    $available = Get-Module -ListAvailable $moduleName | Sort-Object Version -Descending | Select-Object -First 1
                    
                    $modules[$moduleName] = @{
                        'Installed' = if ($installed) { $installed.Version.ToString() } else { $null }
                        'Available' = if ($available) { $available.Version.ToString() } else { $null }
                        'Status' = if ($installed) { 'installed' } elseif ($available) { 'available' } else { 'not_found' }
                    }
                } catch {
                    $modules[$moduleName] = @{
                        'Status' = 'error'
                        'Error' = $_.Exception.Message
                    }
                }
            }
            
            return $modules
            """
            
            result = self.ps_executor.execute_script_and_return_json(module_info_script)
            return result.get('result', {'status': 'failed_to_get_info'})
            
        except Exception as e:
            return {
                'status': 'error', 
                'error': str(e)
            }
    
    def _get_azure_context(self):
        """Get current Azure authentication context."""
        if not self.ps_executor:
            return {'status': 'executor_not_available'}
            
        try:
            azure_context_script = """
            try {
                $context = Get-AzContext -ErrorAction SilentlyContinue
                
                if ($context) {
                    return @{
                        'Authenticated' = $true
                        'Account' = $context.Account.Id
                        'Subscription' = $context.Subscription.Name
                        'SubscriptionId' = $context.Subscription.Id
                        'Tenant' = $context.Tenant.Id
                        'Environment' = $context.Environment.Name
                    }
                } else {
                    return @{
                        'Authenticated' = $false
                    }
                }
            } catch {
                return @{
                    'Status' = 'error'
                    'Error' = $_.Exception.Message
                }
            }
            """
            
            result = self.ps_executor.execute_script_and_return_json(azure_context_script)
            return result.get('result', {'status': 'failed_to_get_info'})
            
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e)
            }
    
    def _get_system_info(self):
        """Get basic system information."""
        import platform
        import sys
        
        return {
            'python_version': sys.version,
            'platform': platform.platform(),
            'architecture': platform.architecture(),
            'system': platform.system(),
            'cli_version': 'unknown'  # Could be populated from CLI version info
        }

def handle_migrate_error(error_message, exception=None, context=None, show_suggestions=True, enable_diagnostics=False):
    """
    Handle Azure Migrate CLI errors with classification and recovery suggestions.
    
    Args:
        error_message: The error message
        exception: The original exception (optional)
        context: Additional context (optional)
        show_suggestions: Whether to show recovery suggestions
        enable_diagnostics: Whether to show detailed diagnostics
        
    Raises:
        CLIError: A formatted error with recovery suggestions
    """
    # Classify the error
    category = ErrorClassifier.classify_error(error_message, exception)
    suggestions = ErrorClassifier.get_recovery_suggestions(category)
    
    # Build the error message
    formatted_message = f"Azure Migrate Error: {error_message}"
    
    if show_suggestions and suggestions:
        formatted_message += "\n\nSuggested Solutions:"
        for i, suggestion in enumerate(suggestions, 1):
            formatted_message += f"\n  {i}. {suggestion}"
    
    if enable_diagnostics:
        diagnostic_info = ErrorClassifier.create_diagnostic_info(error_message, exception, context)
        formatted_message += f"\n\nError Category: {diagnostic_info['error_category']}"
        
        if diagnostic_info.get('trace'):
            formatted_message += f"\n\nDetailed Trace:\n{diagnostic_info['trace']}"
    
    # Log the error for debugging
    logger.error(f"Migrate CLI Error - Category: {category.value}, Message: {error_message}")
    if exception:
        logger.debug(f"Exception details: {exception}")
        
    raise CLIError(formatted_message)
