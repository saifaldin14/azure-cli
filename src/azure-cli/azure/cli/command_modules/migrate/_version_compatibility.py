# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""
Version compatibility management for Azure Migrate CLI module.
Handles PowerShell module version checking and compatibility mapping.
"""

from packaging import version
from knack.log import get_logger

logger = get_logger(__name__)

# Supported PowerShell module versions
SUPPORTED_MODULES = {
    "Az.Migrate": {
        "minimum_version": "2.0.0",
        "recommended_version": "2.2.0",
        "maximum_version": "3.0.0",
        "breaking_changes": {
            "2.1.0": ["Parameter name changes in Get-AzMigrateDiscoveredServer"],
            "2.5.0": ["New required parameter in New-AzMigrateServerReplication"]
        }
    },
    "Az.StackHCI": {
        "minimum_version": "1.0.0", 
        "recommended_version": "1.4.0",
        "maximum_version": "2.0.0",
        "breaking_changes": {}
    },
    "Az.Accounts": {
        "minimum_version": "2.0.0",
        "recommended_version": "2.12.0", 
        "maximum_version": "3.0.0",
        "breaking_changes": {}
    },
    "Az.Profile": {
        "minimum_version": "1.0.0",
        "recommended_version": "1.2.0",
        "maximum_version": "2.0.0", 
        "breaking_changes": {}
    },
    "Az.Resources": {
        "minimum_version": "4.0.0",
        "recommended_version": "6.0.0",
        "maximum_version": "7.0.0",
        "breaking_changes": {}
    }
}

class VersionCompatibilityChecker:
    """Manages version compatibility checking for PowerShell modules."""
    
    def __init__(self, powershell_executor):
        self.ps_executor = powershell_executor
        self._module_versions = {}
        
    def check_module_version(self, module_name, installed_version=None):
        """
        Check if a PowerShell module version is compatible.
        
        Args:
            module_name: Name of the PowerShell module
            installed_version: Version string, or None to auto-detect
            
        Returns:
            dict: {
                'compatible': bool,
                'installed_version': str,
                'recommended_version': str,
                'issues': list,
                'recommendations': list
            }
        """
        if module_name not in SUPPORTED_MODULES:
            return {
                'compatible': False,
                'installed_version': installed_version or 'Unknown',
                'recommended_version': 'Unknown',
                'issues': [f'Module {module_name} is not officially supported'],
                'recommendations': [f'Use one of: {", ".join(SUPPORTED_MODULES.keys())}']
            }
            
        module_config = SUPPORTED_MODULES[module_name]
        
        # Auto-detect version if not provided
        if not installed_version:
            installed_version = self._get_installed_version(module_name)
            
        if not installed_version:
            return {
                'compatible': False,
                'installed_version': 'Not installed',
                'recommended_version': module_config['recommended_version'],
                'issues': [f'Module {module_name} is not installed'],
                'recommendations': [f'Install with: Install-Module {module_name} -Force']
            }
        
        result = {
            'installed_version': installed_version,
            'recommended_version': module_config['recommended_version'],
            'issues': [],
            'recommendations': []
        }
        
        try:
            installed_ver = version.parse(installed_version)
            min_ver = version.parse(module_config['minimum_version'])
            max_ver = version.parse(module_config['maximum_version'])
            recommended_ver = version.parse(module_config['recommended_version'])
            
            # Check version bounds
            if installed_ver < min_ver:
                result['compatible'] = False
                result['issues'].append(f'Version {installed_version} is below minimum required {module_config["minimum_version"]}')
                result['recommendations'].append(f'Update to at least version {module_config["minimum_version"]}')
            elif installed_ver >= max_ver:
                result['compatible'] = False  
                result['issues'].append(f'Version {installed_version} may have breaking changes (max tested: {module_config["maximum_version"]})')
                result['recommendations'].append(f'Consider downgrading to version {module_config["recommended_version"]} for best compatibility')
            else:
                result['compatible'] = True
                
                # Check for known breaking changes
                breaking_changes = []
                for breaking_ver, changes in module_config.get('breaking_changes', {}).items():
                    if installed_ver >= version.parse(breaking_ver):
                        breaking_changes.extend(changes)
                        
                if breaking_changes:
                    result['issues'].extend(breaking_changes)
                    result['recommendations'].append('Review breaking changes and test thoroughly')
                
                # Recommend update if not on recommended version
                if installed_ver < recommended_ver:
                    result['recommendations'].append(f'Consider updating to recommended version {module_config["recommended_version"]}')
                    
        except Exception as e:
            logger.warning(f"Failed to parse version {installed_version} for {module_name}: {e}")
            result['compatible'] = False
            result['issues'].append(f'Invalid version format: {installed_version}')
            result['recommendations'].append('Reinstall the module with a valid version')
            
        return result
    
    def check_all_modules(self):
        """
        Check compatibility of all required PowerShell modules.
        
        Returns:
            dict: {
                'overall_compatible': bool,
                'modules': dict of module_name -> compatibility_result,
                'critical_issues': list,
                'recommendations': list
            }
        """
        results = {
            'overall_compatible': True,
            'modules': {},
            'critical_issues': [],
            'recommendations': []
        }
        
        for module_name in SUPPORTED_MODULES:
            module_result = self.check_module_version(module_name)
            results['modules'][module_name] = module_result
            
            if not module_result['compatible']:
                results['overall_compatible'] = False
                results['critical_issues'].extend(module_result['issues'])
                
            results['recommendations'].extend(module_result['recommendations'])
            
        return results
    
    def _get_installed_version(self, module_name):
        """Get the installed version of a PowerShell module."""
        if module_name in self._module_versions:
            return self._module_versions[module_name]
            
        version_script = f"""
        try {{
            $module = Get-InstalledModule -Name {module_name} -ErrorAction SilentlyContinue
            if ($module) {{
                return $module.Version.ToString()
            }}
            
            # Fallback: check available modules
            $module = Get-Module -ListAvailable {module_name} | Sort-Object Version -Descending | Select-Object -First 1
            if ($module) {{
                return $module.Version.ToString()
            }}
            
            return $null
        }} catch {{
            return $null
        }}
        """
        
        try:
            result = self.ps_executor.execute_script_and_return_json(version_script)
            version_str = result.get('stdout', '').strip()
            
            if version_str and version_str != 'null':
                self._module_versions[module_name] = version_str
                return version_str
                
        except Exception as e:
            logger.debug(f"Failed to get version for {module_name}: {e}")
            
        return None
    
    def get_compatibility_report(self):
        """Generate a detailed compatibility report."""
        results = self.check_all_modules()
        
        report = [
            "Azure Migrate PowerShell Module Compatibility Report",
            "=" * 55,
            ""
        ]
        
        if results['overall_compatible']:
            report.append("✅ Overall Status: COMPATIBLE")
        else:
            report.append("❌ Overall Status: ISSUES FOUND")
            
        report.extend(["", "Module Details:", "-" * 15])
        
        for module_name, module_result in results['modules'].items():
            status = "✅" if module_result['compatible'] else "❌"
            report.append(f"{status} {module_name}")
            report.append(f"   Installed: {module_result['installed_version']}")
            report.append(f"   Recommended: {module_result['recommended_version']}")
            
            if module_result['issues']:
                report.append("   Issues:")
                for issue in module_result['issues']:
                    report.append(f"     - {issue}")
                    
            if module_result['recommendations']:
                report.append("   Recommendations:")
                for rec in module_result['recommendations']:
                    report.append(f"     - {rec}")
                    
            report.append("")
        
        if results['critical_issues']:
            report.extend(["Critical Issues:", "-" * 16])
            for issue in results['critical_issues']:
                report.append(f"❌ {issue}")
            report.append("")
            
        if results['recommendations']:
            report.extend(["Recommendations:", "-" * 15])
            for rec in set(results['recommendations']):  # Remove duplicates
                report.append(f"💡 {rec}")
                
        return "\n".join(report)
