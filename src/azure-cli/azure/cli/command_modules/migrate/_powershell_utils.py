# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from azure.cli.core.util import run_cmd
import platform
from knack.util import CLIError
from knack.log import get_logger
import select
import sys
import threading
import queue
import time
import subprocess
from ._version_compatibility import VersionCompatibilityChecker
from ._error_handling import handle_migrate_error, DiagnosticCollector
from ._command_abstraction import CompatibilityLayer

logger = get_logger(__name__)


class PowerShellExecutor:
    """Cross-platform PowerShell command executor for migration operations."""
    
    def __init__(self):
        self.platform = platform.system().lower()
        self._module_versions = {}
        self._compatibility_layer = None
        self._version_checker = None
        self._diagnostic_collector = None
        
        try:
            self.powershell_cmd = self._get_powershell_command()
            self._initialize_compatibility_layer()
        except CLIError:
            self.powershell_cmd = None
            
    def _initialize_compatibility_layer(self):
        """Initialize the compatibility layer and version management."""
        if self.powershell_cmd:
            try:
                # Initialize version checker
                self._version_checker = VersionCompatibilityChecker(self)
                
                # Get current module versions
                self._module_versions = self._get_all_module_versions()
                
                # Initialize compatibility layer
                self._compatibility_layer = CompatibilityLayer(self, self._module_versions)
                
                # Initialize diagnostic collector
                self._diagnostic_collector = DiagnosticCollector(self)
                
                logger.debug("Compatibility layer initialized successfully")
                
            except Exception as e:
                logger.warning(f"Failed to initialize compatibility layer: {e}")
                # Continue without compatibility layer
                pass
    
    def _get_powershell_command(self):
        """Get the appropriate PowerShell command for the current platform."""
        
        if self.platform == 'windows':
            for cmd in ['powershell.exe', 'powershell']:
                try:
                    result = run_cmd([cmd, '-Command', '$PSVersionTable.PSVersion.ToString()'], 
                                    capture_output=True, timeout=10)
                    if result.returncode == 0:
                        stdout_str = result.stdout.decode('utf-8') if isinstance(result.stdout, bytes) else result.stdout
                        logger.info(f'Found Windows PowerShell: {stdout_str.strip()}')
                        return cmd
                except Exception:
                    logger.debug(f'PowerShell command {cmd} not found')
        else:
            for cmd in ['pwsh']:
                try:
                    result = run_cmd([cmd, '-Command', '$PSVersionTable.PSVersion.ToString()'], 
                                    capture_output=True, timeout=10)
                    if result.returncode == 0:
                        stdout_str = result.stdout.decode('utf-8') if isinstance(result.stdout, bytes) else result.stdout
                        logger.info(f'Found PowerShell Core: {stdout_str.strip()}')
                        return cmd
                except Exception:
                    logger.debug(f'PowerShell command {cmd} not found')
        
        install_guidance = {
            'windows': 'Install PowerShell Core from https://github.com/PowerShell/PowerShell or ensure Windows PowerShell is available.',
            'linux': 'Install PowerShell Core using your package manager:\n' +
                    '  Ubuntu/Debian: sudo apt update && sudo apt install -y powershell\n' +
                    '  CentOS/RHEL: sudo yum install -y powershell\n' +
                    '  Or download from: https://github.com/PowerShell/PowerShell',
            'darwin': 'Install PowerShell Core using Homebrew:\n' +
                     '  brew install powershell\n' +
                     '  Or download from: https://github.com/PowerShell/PowerShell'
        }
        
        guidance = install_guidance.get(self.platform, install_guidance['linux'])
        raise CLIError(f'PowerShell is not available on this {self.platform} system.\n{guidance}')
    
    def check_powershell_availability(self):
        """Check if PowerShell is available and return (is_available, command)."""
        if self.powershell_cmd:
            return True, self.powershell_cmd
        else:
            return False, None
    
    def execute_script(self, script_content, parameters=None):
        """Execute a PowerShell script with optional parameters."""
        try:
            cmd = [self.powershell_cmd, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command']
            
            if parameters:
                param_string = ' '.join([f'-{k} "{v}"' for k, v in parameters.items()])
                script_with_params = f'{script_content} {param_string}'
            else:
                script_with_params = script_content
            
            cmd.append(script_with_params)
            
            logger.debug(f'Executing PowerShell command: {" ".join(cmd)}')
            
            result = run_cmd(
                cmd,
                capture_output=True,
                timeout=300
            )
            
            if result.returncode != 0:
                error_msg = f'PowerShell command failed with exit code {result.returncode}'
                if result.stderr:
                    error_msg += f': {result.stderr}'
                raise CLIError(error_msg)
            
            return {
                'stdout': result.stdout.decode('utf-8') if isinstance(result.stdout, bytes) else result.stdout,
                'stderr': result.stderr.decode('utf-8') if isinstance(result.stderr, bytes) else result.stderr,
                'returncode': result.returncode
            }
            
        except Exception as e:
            if 'timeout' in str(e).lower():
                raise CLIError('PowerShell command timed out after 5 minutes')
            raise CLIError(f'Failed to execute PowerShell command: {str(e)}')
    
    def execute_script_interactive(self, script_content):
        """Execute a PowerShell script with real-time interactive output.
        
        Note: This method uses subprocess.Popen directly for real-time output streaming,
        which is an approved exception to the CLI subprocess guidelines for interactive scenarios.
        """        
        try:
            if not self.powershell_cmd:
                raise CLIError('PowerShell not available')
            
            cmd = [self.powershell_cmd, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', script_content]
            
            logger.debug(f'Executing interactive PowerShell command: {" ".join(cmd)}')
           
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=0,
                universal_newlines=True
            )
            
            output_lines = []
            error_lines = []
            
            if platform.system().lower() == 'windows':
                stdout_queue = queue.Queue()
                stderr_queue = queue.Queue()
                
                def read_stdout():
                    for line in iter(process.stdout.readline, ''):
                        stdout_queue.put(('stdout', line))
                    stdout_queue.put(('stdout', None))
                
                def read_stderr():
                    for line in iter(process.stderr.readline, ''):
                        stderr_queue.put(('stderr', line))
                    stderr_queue.put(('stderr', None))
                
                stdout_thread = threading.Thread(target=read_stdout)
                stderr_thread = threading.Thread(target=read_stderr)
                
                stdout_thread.daemon = True
                stderr_thread.daemon = True
                
                stdout_thread.start()
                stderr_thread.start()
                
                stdout_done = False
                stderr_done = False
                
                while not (stdout_done and stderr_done):
                    try:
                        _, line = stdout_queue.get_nowait()
                        if line is None:
                            stdout_done = True
                        else:
                            line = line.rstrip('\n\r')
                            if line:
                                output_lines.append(line)
                                print(line)
                                sys.stdout.flush()
                    except queue.Empty:
                        pass
                    
                    try:
                        _, line = stderr_queue.get_nowait()
                        if line is None:
                            stderr_done = True
                        else:
                            line = line.rstrip('\n\r')
                            if line:
                                error_lines.append(line)
                                print(f"ERROR: {line}")
                                sys.stdout.flush()
                    except queue.Empty:
                        pass
                    
                    time.sleep(0.01)
                    
                    if process.poll() is not None and stdout_queue.empty() and stderr_queue.empty():
                        break
            
            else:
                while True:
                    reads = [process.stdout.fileno(), process.stderr.fileno()]
                    ret = select.select(reads, [], [])
                    
                    for fd in ret[0]:
                        if fd == process.stdout.fileno():
                            line = process.stdout.readline()
                            if line:
                                line = line.rstrip('\n\r')
                                if line:
                                    output_lines.append(line)
                                    print(line)
                                    sys.stdout.flush()
                        elif fd == process.stderr.fileno():
                            line = process.stderr.readline()
                            if line:
                                line = line.rstrip('\n\r')
                                if line:
                                    error_lines.append(line)
                                    print(f"ERROR: {line}")
                                    sys.stdout.flush()
                    
                    if process.poll() is not None:
                        break
            
            return_code = process.wait()
            
            return {
                'stdout': '\n'.join(output_lines),
                'stderr': '\n'.join(error_lines),
                'returncode': return_code
            }
            
        except Exception as e:
            print(f"ERROR executing PowerShell: {str(e)}")
            return {
                'stdout': '',
                'stderr': str(e),
                'returncode': 1
            }
   
    def execute_azure_authenticated_script(self, script, parameters=None, subscription_id=None):
        """Execute a PowerShell script with Azure authentication."""
        
        auth_prefix = """
        try {
            $context = Get-AzContext
            if (-not $context) {
                Write-Host "No Azure context found. Please run Connect-AzAccount first."
                throw "Azure authentication required"
            }
        } catch {
            Write-Host "Azure PowerShell module not available or not authenticated."
            Write-Host "Please ensure Az.Migrate module is installed and you are authenticated."
            throw "Azure authentication required"
        }
        """
        
        if subscription_id:
            auth_prefix += f"""
        try {{
            Set-AzContext -SubscriptionId "{subscription_id}"
            Write-Host "Subscription context set to: {subscription_id}"
        }} catch {{
            Write-Host "Failed to set subscription context to: {subscription_id}"
            throw "Invalid subscription ID"
        }}
        """
        
        full_script = auth_prefix + "\n" + script
        
        return self.execute_script(full_script, parameters)
    
    def run_preflight_checks(self, check_modules=True, check_auth=True, check_versions=True):
        """
        Run comprehensive pre-flight checks before executing migration commands.
        
        Args:
            check_modules: Whether to check if required modules are installed
            check_auth: Whether to check Azure authentication
            check_versions: Whether to check module version compatibility
            
        Returns:
            dict: Results of pre-flight checks
        """
        results = {
            'overall_status': 'passed',
            'checks': [],
            'errors': [],
            'warnings': [],
            'recommendations': []
        }
        
        try:
            # 1. Check PowerShell availability
            if not self.powershell_cmd:
                results['overall_status'] = 'failed'
                results['errors'].append('PowerShell is not available')
                results['recommendations'].append('Run: az migrate setup-env --install-powershell')
                return results
                
            results['checks'].append('PowerShell availability: ✓')
            
            # 2. Check module installation
            if check_modules:
                module_check = self._check_required_modules()
                results['checks'].extend(module_check['checks'])
                results['errors'].extend(module_check['errors'])
                results['warnings'].extend(module_check['warnings'])
                results['recommendations'].extend(module_check['recommendations'])
                
                if module_check['errors']:
                    results['overall_status'] = 'failed'
                elif module_check['warnings']:
                    if results['overall_status'] != 'failed':
                        results['overall_status'] = 'warning'
            
            # 3. Check version compatibility
            if check_versions and self._version_checker:
                version_check = self._version_checker.check_all_modules()
                
                if not version_check['overall_compatible']:
                    results['overall_status'] = 'failed'
                    results['errors'].extend(version_check['critical_issues'])
                    
                results['recommendations'].extend(version_check['recommendations'])
                
                for module_name, module_result in version_check['modules'].items():
                    status = "✓" if module_result['compatible'] else "✗"
                    results['checks'].append(f"{module_name} version compatibility: {status}")
            
            # 4. Check Azure authentication
            if check_auth:
                auth_check = self.check_azure_authentication()
                
                if auth_check.get('IsAuthenticated', False):
                    results['checks'].append('Azure authentication: ✓')
                else:
                    results['warnings'].append('Azure authentication not verified')
                    results['recommendations'].append('Run: az migrate auth login')
                    if results['overall_status'] == 'passed':
                        results['overall_status'] = 'warning'
                        
        except Exception as e:
            results['overall_status'] = 'failed'
            results['errors'].append(f'Pre-flight check failed: {str(e)}')
            
        return results
    
    def _check_required_modules(self):
        """Check if required PowerShell modules are installed."""
        results = {
            'checks': [],
            'errors': [],
            'warnings': [],
            'recommendations': []
        }
        
        required_modules = ['Az.Migrate', 'Az.Accounts', 'Az.Profile', 'Az.Resources']
        optional_modules = ['Az.StackHCI']
        
        try:
            module_check_script = f"""
            $results = @()
            $moduleNames = @{required_modules + optional_modules}
            
            foreach ($moduleName in $moduleNames) {{
                try {{
                    $installed = Get-InstalledModule -Name $moduleName -ErrorAction SilentlyContinue
                    $available = Get-Module -ListAvailable $moduleName -ErrorAction SilentlyContinue
                    
                    $status = if ($installed) {{ 'installed' }} elseif ($available) {{ 'available' }} else {{ 'not_found' }}
                    $version = if ($installed) {{ $installed.Version.ToString() }} elseif ($available) {{ $available[0].Version.ToString() }} else {{ $null }}
                    
                    $results += @{{
                        'Module' = $moduleName
                        'Status' = $status
                        'Version' = $version
                    }}
                }} catch {{
                    $results += @{{
                        'Module' = $moduleName
                        'Status' = 'error'
                        'Error' = $_.Exception.Message
                    }}
                }}
            }}
            
            return $results
            """
            
            result = self.execute_script_and_return_json(module_check_script)
            modules_info = result.get('result', [])
            
            for module_info in modules_info:
                module_name = module_info.get('Module', 'Unknown')
                status = module_info.get('Status', 'unknown')
                version = module_info.get('Version', 'Unknown')
                
                if status == 'installed':
                    results['checks'].append(f"{module_name} ({version}): ✓")
                elif status == 'available':
                    results['warnings'].append(f"{module_name} is available but not installed")
                    results['recommendations'].append(f"Install {module_name}: Install-Module {module_name} -Force")
                elif status == 'not_found':
                    if module_name in required_modules:
                        results['errors'].append(f"Required module {module_name} not found")
                        results['recommendations'].append(f"Install {module_name}: Install-Module {module_name} -Force")
                    else:
                        results['warnings'].append(f"Optional module {module_name} not found")
                elif status == 'error':
                    error_msg = module_info.get('Error', 'Unknown error')
                    results['warnings'].append(f"Error checking {module_name}: {error_msg}")
                    
        except Exception as e:
            results['errors'].append(f"Failed to check modules: {str(e)}")
            results['recommendations'].append("Run: az migrate powershell update-modules")
            
        return results
    
    def _get_all_module_versions(self):
        """Get versions of all relevant PowerShell modules."""
        versions = {}
        
        try:
            version_script = """
            $modules = @('Az.Migrate', 'Az.StackHCI', 'Az.Accounts', 'Az.Profile', 'Az.Resources')
            $result = @{}
            
            foreach ($moduleName in $modules) {
                try {
                    $installed = Get-InstalledModule -Name $moduleName -ErrorAction SilentlyContinue
                    if ($installed) {
                        $result[$moduleName] = $installed.Version.ToString()
                    } else {
                        $available = Get-Module -ListAvailable $moduleName | Sort-Object Version -Descending | Select-Object -First 1
                        if ($available) {
                            $result[$moduleName] = $available.Version.ToString()
                        }
                    }
                } catch {
                    # Ignore errors for individual modules
                }
            }
            
            return $result
            """
            
            result = self.execute_script_and_return_json(version_script)
            versions = result.get('result', {})
            
        except Exception as e:
            logger.debug(f"Failed to get module versions: {e}")
            
        return versions
    
    def execute_script_and_return_json(self, script_content):
        """Execute a PowerShell script and return JSON result."""
        wrapped_script = f"""
        try {{
            $result = {script_content}
            @{{ 'result' = $result; 'success' = $true }} | ConvertTo-Json -Depth 10
        }} catch {{
            @{{ 'error' = $_.Exception.Message; 'success' = $false }} | ConvertTo-Json -Depth 10
        }}
        """
        
        execution_result = self.execute_script(wrapped_script)
        
        try:
            import json
            return json.loads(execution_result['stdout'])
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Failed to parse JSON result: {e}")
            return {'success': False, 'error': 'Failed to parse result'}
    
    def execute_with_error_handling(self, script_content, operation_name="PowerShell operation", enable_diagnostics=False):
        """
        Execute a PowerShell script with enhanced error handling.
        
        Args:
            script_content: PowerShell script to execute
            operation_name: Human-readable operation name for error messages
            enable_diagnostics: Whether to collect diagnostic information
            
        Returns:
            Execution result or raises CLIError with helpful suggestions
        """
        try:
            # Run pre-flight checks if compatibility layer is available
            if self._compatibility_layer:
                preflight_result = self.run_preflight_checks(check_auth=False)  # Skip auth check for now
                
                if preflight_result['overall_status'] == 'failed':
                    error_msg = f"Pre-flight checks failed for {operation_name}"
                    context = {'preflight_errors': preflight_result['errors']}
                    handle_migrate_error(error_msg, context=context, enable_diagnostics=enable_diagnostics)
                    
                elif preflight_result['overall_status'] == 'warning':
                    for warning in preflight_result['warnings']:
                        logger.warning(f"Pre-flight warning: {warning}")
            
            # Execute the script
            return self.execute_script_interactive(script_content)
            
        except Exception as e:
            # Enhanced error handling
            context = {
                'operation': operation_name,
                'platform': self.platform,
                'powershell_cmd': self.powershell_cmd
            }
            
            if enable_diagnostics and self._diagnostic_collector:
                context['diagnostics'] = self._diagnostic_collector.collect_environment_info()
                
            handle_migrate_error(str(e), exception=e, context=context, enable_diagnostics=enable_diagnostics)
    
    def get_compatibility_layer(self):
        """Get the compatibility layer instance."""
        return self._compatibility_layer
    
    def get_version_checker(self):
        """Get the version compatibility checker."""
        return self._version_checker
    
    def get_diagnostic_collector(self):
        """Get the diagnostic collector."""
        return self._diagnostic_collector
    
def get_powershell_executor():
    """Get a PowerShell executor instance."""
    return PowerShellExecutor()
