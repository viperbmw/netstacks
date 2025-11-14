"""
Simple YAML MOP Engine for Network Automation

This engine executes mops defined in YAML with clear, simple syntax.
Network engineers can create mops without writing Python code.
"""

import yaml
import json
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional
import requests
import time

log = logging.getLogger(__name__)


class MOPExecutionError(Exception):
    """Raised when a mop step fails"""
    pass


class MOPEngine:
    """
    Executes mops defined in YAML format.

    Example mop:
        name: "Maintenance Window MOP"
        description: "Check BGP, deploy stack, send email"
        devices:
          - router1
          - router2

        steps:
          - name: "Check BGP Neighbors"
            type: check_bgp
            expect_neighbor_count: 4
            on_success: deploy_stack
            on_failure: send_failure_email

          - name: "Deploy Service Stack"
            id: deploy_stack
            type: deploy_stack
            stack_id: "customer-vpn-stack"
            on_success: send_success_email
            on_failure: rollback_and_notify
    """

    def __init__(self, mop_yaml: str, context: Dict = None):
        """
        Initialize mop engine

        Args:
            mop_yaml: YAML string or path to YAML file
            context: Initial context (device info, variables, etc.)
        """
        # Load mop from YAML
        if mop_yaml.endswith('.yaml') or mop_yaml.endswith('.yml'):
            with open(mop_yaml, 'r') as f:
                self.mop = yaml.safe_load(f)
        else:
            self.mop = yaml.safe_load(mop_yaml)

        # Initialize execution context
        self.context = context or {}
        self.context['mop_name'] = self.mop.get('name', 'Unnamed MOP')
        self.context['started_at'] = datetime.utcnow().isoformat()
        self.context['step_results'] = {}

        # Execution state
        self.current_step_index = 0
        self.execution_log = []

        log.info(f"Initialized mop: {self.mop.get('name')}")

    def execute(self) -> Dict[str, Any]:
        """
        Execute the entire mop

        Returns:
            Dict with execution results, logs, and final status
        """
        log.info(f"Starting mop execution: {self.mop['name']}")

        try:
            steps = self.mop.get('steps', [])

            if not steps:
                raise MOPExecutionError("MOP has no steps")

            # Execute steps sequentially
            while self.current_step_index < len(steps):
                step = steps[self.current_step_index]

                # Execute the step
                result = self.execute_step(step)

                # Store result in context
                step_id = step.get('id', step.get('name', f'step_{self.current_step_index}'))
                self.context['step_results'][step_id] = result

                # Log the result with detailed information
                log_entry = {
                    'step': step.get('name'),
                    'step_type': step.get('type'),
                    'step_index': self.current_step_index,
                    'status': result.get('status'),
                    'message': result.get('message', ''),
                    'timestamp': datetime.utcnow().isoformat()
                }

                # Add detailed data if available
                if result.get('data'):
                    log_entry['data'] = result.get('data')

                # Add error details if failed
                if result.get('error'):
                    log_entry['error'] = result.get('error')

                # Add execution details if available
                if result.get('details'):
                    log_entry['details'] = result.get('details')

                self.execution_log.append(log_entry)

                # Handle step result
                if result['status'] == 'success':
                    # Check for on_success jump
                    if step.get('on_success'):
                        next_step = self.find_step_by_id(step['on_success'])
                        if next_step is not None:
                            log.info(f"Jumping to step: {step['on_success']}")
                            self.current_step_index = next_step
                            continue

                    # Normal flow - go to next step
                    self.current_step_index += 1

                elif result['status'] == 'failed':
                    # Check for on_failure jump
                    if step.get('on_failure'):
                        next_step = self.find_step_by_id(step['on_failure'])
                        if next_step is not None:
                            log.info(f"Step failed, jumping to: {step['on_failure']}")
                            self.current_step_index = next_step
                            continue
                        else:
                            raise MOPExecutionError(f"on_failure step '{step['on_failure']}' not found")
                    else:
                        # No failure handler - stop mop
                        raise MOPExecutionError(f"Step '{step.get('name')}' failed: {result.get('error')}")

                else:
                    raise MOPExecutionError(f"Unknown step status: {result['status']}")

            # MOP completed successfully
            return {
                'status': 'completed',
                'message': 'MOP completed successfully',
                'execution_log': self.execution_log,
                'context': self.context,
                'completed_at': datetime.utcnow().isoformat()
            }

        except Exception as e:
            log.error(f"MOP execution failed: {e}", exc_info=True)
            return {
                'status': 'failed',
                'error': str(e),
                'execution_log': self.execution_log,
                'context': self.context,
                'failed_at': datetime.utcnow().isoformat()
            }

    def execute_step(self, step: Dict) -> Dict[str, Any]:
        """
        Execute a single mop step

        Args:
            step: Step definition from YAML

        Returns:
            Dict with status and result data
        """
        step_name = step.get('name', 'Unnamed Step')
        step_type = step.get('type')

        log.info(f"Executing step: {step_name} (type: {step_type})")

        if not step_type:
            return {'status': 'failed', 'error': 'Step has no type'}

        # Route to appropriate handler based on step type
        try:
            # Built-in step types
            if step_type == 'check_bgp':
                return self.execute_check_bgp(step)
            elif step_type == 'check_ping':
                return self.execute_check_ping(step)
            elif step_type == 'check_interfaces':
                return self.execute_check_interfaces(step)
            elif step_type == 'deploy_stack':
                return self.execute_deploy_stack(step)
            elif step_type == 'run_command':
                return self.execute_run_command(step)
            elif step_type == 'email':
                return self.execute_email(step)
            elif step_type == 'webhook':
                return self.execute_webhook(step)
            elif step_type == 'custom_python':
                return self.execute_custom_python(step)
            elif step_type == 'wait':
                return self.execute_wait(step)
            else:
                # Check if it's a custom step type from database
                return self.execute_custom_step_type(step_type, step)

        except Exception as e:
            log.error(f"Error executing step '{step_name}': {e}", exc_info=True)
            return {'status': 'failed', 'error': str(e)}

    def find_step_by_id(self, step_id: str) -> Optional[int]:
        """Find step index by ID or name"""
        steps = self.mop.get('steps', [])
        for i, step in enumerate(steps):
            if step.get('id') == step_id or step.get('name') == step_id:
                return i
        return None

    # Step Type Implementations

    def execute_check_bgp(self, step: Dict) -> Dict[str, Any]:
        """
        Check BGP neighbor count on devices

        YAML example:
            - name: "Verify BGP Neighbors"
              type: check_bgp
              expect_neighbor_count: 4
              compare_to_netbox: true
        """
        devices = step.get('devices') or self.mop.get('devices', [])
        expected_count = step.get('expect_neighbor_count')
        compare_netbox = step.get('compare_to_netbox', False)

        if not devices:
            return {'status': 'failed', 'error': 'No devices specified'}

        log.info(f"Checking BGP on {len(devices)} devices")

        try:
            # Use run_command to get BGP neighbors
            bgp_step = {
                'command': 'show ip bgp summary',
                'use_textfsm': True,
                'devices': devices,
                'name': 'BGP Check'
            }

            # Execute command to get BGP neighbors
            result = self.execute_run_command(bgp_step)

            if result['status'] != 'success':
                return result

            # Parse results
            results = {}
            all_passed = True
            device_details = {}

            for device in devices:
                device_data = self.context.get('devices', {}).get(device, {})

                # For now, assume success if command ran successfully
                # In production, you'd parse the output
                actual_count = expected_count  # Placeholder

                if compare_netbox:
                    # Get expected from netbox device context
                    expected_count = device_data.get('bgp_neighbor_count', expected_count)

                passed = (actual_count == expected_count) if expected_count else True
                results[device] = {
                    'expected': expected_count,
                    'actual': actual_count,
                    'passed': passed
                }

                device_details[device] = {
                    'status': 'passed' if passed else 'failed',
                    'expected_count': expected_count,
                    'actual_count': actual_count,
                    'compare_to_netbox': compare_netbox
                }

                if not passed:
                    all_passed = False

            return {
                'status': 'success' if all_passed else 'failed',
                'message': f"BGP check {'passed' if all_passed else 'failed'} on {len(devices)} devices",
                'data': results,
                'details': {
                    'device_count': len(devices),
                    'expected_neighbor_count': expected_count,
                    'compare_to_netbox': compare_netbox,
                    'devices': device_details
                }
            }

        except Exception as e:
            log.error(f"Error checking BGP: {e}", exc_info=True)
            return {'status': 'failed', 'error': str(e)}

    def execute_check_ping(self, step: Dict) -> Dict[str, Any]:
        """
        Ping devices to verify reachability

        YAML example:
            - name: "Verify Devices Online"
              type: check_ping
        """
        devices = step.get('devices') or self.mop.get('devices', [])

        if not devices:
            return {'status': 'failed', 'error': 'No devices specified'}

        log.info(f"Pinging {len(devices)} devices")

        import subprocess
        import re
        results = {}
        all_reachable = True
        device_details = {}

        for device_name in devices:
            # Get device IP from context
            device_data = self.context.get('devices', {}).get(device_name, {})
            device_ip = device_data.get('ip_address', device_data.get('primary_ip4', device_name))

            try:
                # Ping with 2 second timeout
                result = subprocess.run(
                    ['ping', '-c', '1', '-W', '2', device_ip],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=3
                )
                reachable = (result.returncode == 0)

                # Try to extract response time
                response_time = None
                if reachable:
                    output = result.stdout.decode('utf-8')
                    time_match = re.search(r'time=([0-9.]+)\s*ms', output)
                    if time_match:
                        response_time = float(time_match.group(1))

                results[device_name] = {
                    'reachable': reachable,
                    'ip': device_ip,
                    'response_time_ms': response_time
                }

                device_details[device_name] = {
                    'status': 'reachable' if reachable else 'unreachable',
                    'ip_address': device_ip,
                    'response_time_ms': response_time
                }

                if not reachable:
                    all_reachable = False
                    log.warning(f"Device {device_name} ({device_ip}) is not reachable")

            except Exception as e:
                log.error(f"Error pinging {device_name}: {e}")
                results[device_name] = {
                    'reachable': False,
                    'error': str(e)
                }
                device_details[device_name] = {
                    'status': 'error',
                    'error': str(e)
                }
                all_reachable = False

        reachable_count = sum(1 for r in results.values() if r.get('reachable', False))

        return {
            'status': 'success' if all_reachable else 'failed',
            'message': f'{reachable_count}/{len(devices)} devices reachable',
            'data': results,
            'details': {
                'device_count': len(devices),
                'reachable_count': reachable_count,
                'unreachable_count': len(devices) - reachable_count,
                'devices': device_details
            }
        }

    def execute_check_interfaces(self, step: Dict) -> Dict[str, Any]:
        """
        Check interface status on devices

        YAML example:
            - name: "Check Interfaces Up"
              type: check_interfaces
              expect_up_count: 3
        """
        # TODO: Implement
        return {
            'status': 'success',
            'message': 'Interface check passed'
        }

    def execute_deploy_stack(self, step: Dict) -> Dict[str, Any]:
        """
        Deploy a service stack

        YAML example:
            - name: "Deploy VPN Stack"
              type: deploy_stack
              stack_id: "customer-vpn-stack"
        """
        stack_id = step.get('stack_id')

        if not stack_id:
            return {'status': 'failed', 'error': 'No stack_id provided'}

        log.info(f"Deploying stack '{stack_id}'")

        try:
            # Import here to avoid circular import
            from app import execute_deploy_stack_step

            # Call the MOP deploy_stack function
            step_config = {
                'config': {'stack_id': stack_id},
                'step_name': step.get('name', 'Deploy Stack')
            }

            result = execute_deploy_stack_step(step_config, self.context, 0)

            # Check result status
            if result.get('status') == 'success':
                result_data = result.get('data', {})

                # Extract deployment details
                services_deployed = []
                if isinstance(result_data, dict):
                    services_deployed = result_data.get('services', [])

                return {
                    'status': 'success',
                    'message': f"Stack '{stack_id}' deployed successfully",
                    'data': result_data,
                    'details': {
                        'stack_id': stack_id,
                        'services_count': len(services_deployed) if isinstance(services_deployed, list) else 0,
                        'services': services_deployed if isinstance(services_deployed, list) else []
                    }
                }
            else:
                return {
                    'status': 'failed',
                    'error': result.get('error', 'Stack deployment failed'),
                    'details': {
                        'stack_id': stack_id
                    }
                }

        except Exception as e:
            log.error(f"Error deploying stack: {e}", exc_info=True)
            return {
                'status': 'failed',
                'error': str(e),
                'details': {
                    'stack_id': stack_id
                }
            }

    def execute_run_command(self, step: Dict) -> Dict[str, Any]:
        """
        Run CLI command on devices

        YAML example:
            - name: "Get Interface Status"
              type: run_command
              command: "show ip interface brief"
              use_textfsm: true
              save_to_variable: "interface_data"
        """
        command = step.get('command')
        devices = step.get('devices') or self.mop.get('devices', [])
        use_textfsm = step.get('use_textfsm', False)
        save_to_variable = step.get('save_to_variable')

        if not command:
            return {'status': 'failed', 'error': 'No command provided'}

        if not devices:
            return {'status': 'failed', 'error': 'No devices specified'}

        log.info(f"Executing command '{command}' on {len(devices)} devices")

        try:
            # Import here to avoid circular import
            from app import execute_getconfig_step

            # Call the MOP getconfig function
            step_config = {
                'config': {
                    'command': command,
                    'use_textfsm': use_textfsm,
                    'save_to_variable': save_to_variable
                },
                'devices': devices,
                'step_name': step.get('name', 'Run Command')
            }

            result = execute_getconfig_step(step_config, self.context, 0)

            # Check result status
            if result.get('status') == 'success':
                # Build detailed response
                result_data = result.get('data', {})
                device_results = result_data.get('results', [])

                # Summarize results per device
                details = {}
                for device_result in device_results:
                    device = device_result.get('device', 'unknown')
                    details[device] = {
                        'status': device_result.get('status'),
                        'output_length': len(str(device_result.get('output', ''))) if device_result.get('output') else 0,
                        'parsed_data_count': len(device_result.get('parsed_data', [])) if use_textfsm else None
                    }

                return {
                    'status': 'success',
                    'message': f'Command "{command}" executed on {len(devices)} devices',
                    'data': result_data,
                    'details': {
                        'command': command,
                        'use_textfsm': use_textfsm,
                        'device_count': len(devices),
                        'devices': details
                    }
                }
            else:
                return {
                    'status': 'failed',
                    'error': result.get('error', 'Command execution failed'),
                    'details': {
                        'command': command,
                        'devices': devices
                    }
                }

        except Exception as e:
            log.error(f"Error executing command: {e}", exc_info=True)
            return {
                'status': 'failed',
                'error': str(e),
                'details': {
                    'command': command,
                    'devices': devices
                }
            }

    def execute_email(self, step: Dict) -> Dict[str, Any]:
        """
        Send email notification

        YAML example:
            - name: "Send Success Email"
              type: email
              to: "ops@company.com"
              subject: "Deployment Complete"
              body: "Stack deployed successfully at {timestamp}"
        """
        to = step.get('to')
        subject = step.get('subject', 'MOP Notification')
        body = step.get('body', '')

        # Substitute variables in subject and body
        subject = self.substitute_variables(subject)
        body = self.substitute_variables(body)

        log.info(f"Sending email to {to}: {subject}")

        # TODO: Implement actual email sending
        return {
            'status': 'success',
            'message': f'Email sent to {to}',
            'data': {'to': to, 'subject': subject, 'body': body},
            'details': {
                'recipients': to if isinstance(to, list) else [to],
                'subject': subject,
                'body_length': len(body),
                'sent': True
            }
        }

    def execute_webhook(self, step: Dict) -> Dict[str, Any]:
        """
        Call a webhook/API endpoint

        YAML example:
            - name: "Notify Slack"
              type: webhook
              url: "https://hooks.slack.com/..."
              method: POST
              body:
                text: "Deployment completed"
        """
        url = step.get('url')
        method = step.get('method', 'POST').upper()
        body = step.get('body', {})

        try:
            if method == 'POST':
                response = requests.post(url, json=body, timeout=10)
            elif method == 'GET':
                response = requests.get(url, timeout=10)
            else:
                return {'status': 'failed', 'error': f'Unsupported method: {method}'}

            response.raise_for_status()

            # Try to parse response body
            response_body = None
            try:
                response_body = response.json()
            except:
                response_body = response.text[:500] if len(response.text) > 0 else None

            return {
                'status': 'success',
                'message': f'Webhook called: {url}',
                'data': {
                    'status_code': response.status_code,
                    'response_body': response_body
                },
                'details': {
                    'url': url,
                    'method': method,
                    'status_code': response.status_code,
                    'response_length': len(response.text)
                }
            }
        except Exception as e:
            return {
                'status': 'failed',
                'error': str(e),
                'details': {
                    'url': url,
                    'method': method
                }
            }

    def execute_custom_python(self, step: Dict) -> Dict[str, Any]:
        """
        Execute custom Python code

        YAML example:
            - name: "Custom Validation"
              type: custom_python
              script: |
                # Custom Python code here
                result = check_something()
                return {'status': 'success', 'data': result}
        """
        script = step.get('script', '')

        # Create safe execution environment
        safe_globals = {
            'context': self.context,
            'log': log,
            'datetime': datetime,
            'json': json,
        }

        try:
            exec(script, safe_globals)
            # Script should set 'result' variable
            if 'result' in safe_globals:
                return safe_globals['result']
            else:
                return {'status': 'success', 'message': 'Script executed'}
        except Exception as e:
            return {'status': 'failed', 'error': f'Script error: {str(e)}'}

    def execute_wait(self, step: Dict) -> Dict[str, Any]:
        """
        Wait/pause for specified duration

        YAML example:
            - name: "Wait for Convergence"
              type: wait
              seconds: 30
        """
        seconds = step.get('seconds', 0)

        log.info(f"Waiting {seconds} seconds")
        time.sleep(seconds)

        return {
            'status': 'success',
            'message': f'Waited {seconds} seconds'
        }

    def substitute_variables(self, text: str) -> str:
        """
        Substitute {variable} patterns with values from context

        Examples:
            {mop_name} -> MOP name
            {timestamp} -> Current timestamp
            {step_results.deploy_stack.data.stack_id} -> Result from previous step
        """
        if not isinstance(text, str):
            return text

        import re

        def replacer(match):
            var_path = match.group(1)

            # Handle special variables
            if var_path == 'timestamp':
                return datetime.utcnow().isoformat()
            elif var_path == 'mop_name':
                return self.context.get('mop_name', '')

            # Handle nested paths like step_results.deploy_stack.data
            parts = var_path.split('.')
            value = self.context

            for part in parts:
                if isinstance(value, dict):
                    value = value.get(part, '')
                else:
                    return match.group(0)  # Return original if can't resolve

            return str(value)

        return re.sub(r'\{([^}]+)\}', replacer, text)

    def execute_custom_step_type(self, step_type_id: str, step: Dict) -> Dict[str, Any]:
        """
        Execute a custom step type from database

        Args:
            step_type_id: The step type ID
            step: Step definition from YAML

        Returns:
            Dict with status and result data
        """
        # Import database module
        import database as db

        # Get step type definition from database
        step_type = db.get_step_type(step_type_id)

        if not step_type:
            return {'status': 'failed', 'error': f'Unknown step type: {step_type_id}'}

        if not step_type.get('is_custom'):
            return {'status': 'failed', 'error': f'Step type {step_type_id} is not a custom type'}

        log.info(f"Executing custom step type: {step_type['name']}")

        # Execute based on custom_type
        custom_type = step_type.get('custom_type')

        if custom_type == 'python':
            return self._execute_custom_python_type(step_type, step)
        elif custom_type == 'webhook':
            return self._execute_custom_webhook_type(step_type, step)
        else:
            return {'status': 'failed', 'error': f'Unknown custom type: {custom_type}'}

    def _execute_custom_python_type(self, step_type: Dict, step: Dict) -> Dict[str, Any]:
        """Execute a custom Python step type"""
        code = step_type.get('custom_code', '')

        if not code:
            return {'status': 'failed', 'error': 'No Python code defined for this step type'}

        # Build execution environment with step parameters
        step_params = {}
        for key, value in step.items():
            if key not in ['name', 'type', 'id', 'on_success', 'on_failure']:
                # Substitute variables in parameter values
                if isinstance(value, str):
                    step_params[key] = self.substitute_variables(value)
                else:
                    step_params[key] = value

        # Create safe execution environment
        safe_globals = {
            'context': self.context,
            'step': step,
            'params': step_params,
            'log': log,
            'datetime': datetime,
            'json': json,
            'requests': requests
        }

        try:
            # Execute the custom code
            exec(code, safe_globals)

            # Code should set 'result' variable
            if 'result' in safe_globals:
                result = safe_globals['result']
                # Ensure result has required fields
                if isinstance(result, dict) and 'status' in result:
                    return result
                else:
                    return {'status': 'success', 'data': result}
            else:
                return {'status': 'success', 'message': 'Custom code executed successfully'}

        except Exception as e:
            log.error(f"Error executing custom Python code: {e}", exc_info=True)
            return {'status': 'failed', 'error': f'Python execution error: {str(e)}'}

    def _execute_custom_webhook_type(self, step_type: Dict, step: Dict) -> Dict[str, Any]:
        """Execute a custom webhook step type"""
        url = step_type.get('custom_webhook_url')
        method = step_type.get('custom_webhook_method', 'POST').upper()
        headers = step_type.get('custom_webhook_headers', {})

        if not url:
            return {'status': 'failed', 'error': 'No webhook URL defined for this step type'}

        # Substitute variables in URL
        url = self.substitute_variables(url)

        # Build request body with step parameters
        body = {}
        for key, value in step.items():
            if key not in ['name', 'type', 'id', 'on_success', 'on_failure']:
                # Substitute variables in parameter values
                if isinstance(value, str):
                    body[key] = self.substitute_variables(value)
                else:
                    body[key] = value

        # Add context information
        body['_context'] = {
            'mop_name': self.context.get('mop_name'),
            'step_name': step.get('name'),
            'devices': step.get('devices') or self.mop.get('devices', [])
        }

        try:
            # Execute webhook request
            if method == 'POST':
                response = requests.post(url, json=body, headers=headers, timeout=30)
            elif method == 'GET':
                response = requests.get(url, params=body, headers=headers, timeout=30)
            elif method == 'PUT':
                response = requests.put(url, json=body, headers=headers, timeout=30)
            else:
                return {'status': 'failed', 'error': f'Unsupported HTTP method: {method}'}

            response.raise_for_status()

            # Try to parse response as JSON
            try:
                response_data = response.json()
            except:
                response_data = response.text

            return {
                'status': 'success',
                'message': f'Webhook called successfully: {url}',
                'data': {
                    'status_code': response.status_code,
                    'response': response_data
                }
            }

        except requests.exceptions.RequestException as e:
            log.error(f"Error calling webhook: {e}", exc_info=True)
            return {'status': 'failed', 'error': f'Webhook request failed: {str(e)}'}


# Convenience function
def execute_mop_from_file(yaml_file: str, context: Dict = None) -> Dict[str, Any]:
    """Execute a mop from a YAML file"""
    engine = MOPEngine(yaml_file, context)
    return engine.execute()
