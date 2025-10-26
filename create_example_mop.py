#!/usr/bin/env python3
"""
Create an example MOP that demonstrates:
1. GetConfig with TextFSM to get interface status
2. Code step to check for at least 3 interfaces that are up/up
3. API call to Netbox to get interface IDs
4. Code step to combine variables into a report
"""

import sys
import json
from database import get_db

def create_example_mop():
    """Create an example MOP with all step types"""

    mop_data = {
        'name': 'Interface Status Report',
        'description': 'Example MOP: Get interface status with TextFSM, validate at least 3 interfaces are up, query Netbox for interface IDs, and generate a report',
        'devices': json.dumps(['bms01-bidev.nae05.gi-nw.viasat.io', 'dmsp01-cidev.nae05.gi-nw.viasat.io'])
    }

    steps = [
        {
            'step_name': 'Get Interface Status',
            'step_type': 'getconfig',
            'step_order': 0,
            'enabled': 1,
            'devices': json.dumps(['bms01-bidev.nae05.gi-nw.viasat.io', 'dmsp01-cidev.nae05.gi-nw.viasat.io']),
            'config': json.dumps({
                'command': 'show ip interface brief',
                'use_textfsm': True,
                'save_to_variable': 'interface_status'
            }),
            'description': 'Retrieve interface status using TextFSM parsing'
        },
        {
            'step_name': 'Validate Interface Count',
            'step_type': 'code',
            'step_order': 1,
            'enabled': 1,
            'devices': json.dumps([]),
            'config': json.dumps({
                'script': '''# Check if at least 3 interfaces are up/up on each device
import json

results = {}
validation_passed = True

for device_name, device_data in context['devices'].items():
    # Get interface status from previous step
    interface_status = device_data.get('interface_status', [])

    # Count interfaces that are up/up
    up_interfaces = []
    if isinstance(interface_status, list):
        for intf in interface_status:
            # TextFSM returns dict with keys like 'interface', 'ip_address', 'status', 'protocol'
            status = intf.get('status', '').lower()
            protocol = intf.get('protocol', '').lower()
            if 'up' in status and 'up' in protocol:
                up_interfaces.append(intf.get('interface', 'unknown'))

    results[device_name] = {
        'total_interfaces': len(interface_status),
        'up_interfaces': up_interfaces,
        'up_count': len(up_interfaces),
        'validation_passed': len(up_interfaces) >= 3
    }

    if len(up_interfaces) < 3:
        validation_passed = False

# Store results
context['validation_results'] = results
context['all_devices_validated'] = validation_passed

# Return summary
output = f"Validation Results:\\n"
for device, data in results.items():
    output += f"  {device}: {data['up_count']}/{data['total_interfaces']} interfaces up - {'PASS' if data['validation_passed'] else 'FAIL'}\\n"

print(output)
''',
                'save_to_variable': 'validation_results'
            }),
            'description': 'Check that each device has at least 3 interfaces in up/up state'
        },
        {
            'step_name': 'Get Netbox Interface IDs',
            'step_type': 'api',
            'step_order': 2,
            'enabled': 1,
            'devices': json.dumps(['bms01-bidev.nae05.gi-nw.viasat.io', 'dmsp01-cidev.nae05.gi-nw.viasat.io']),
            'config': json.dumps({
                'resource_id': 'netbox',
                'endpoint': '/api/dcim/interfaces/?device={{device_name}}',
                'method': 'GET',
                'save_to_variable': 'netbox_interfaces'
            }),
            'description': 'Query Netbox API to get interface IDs for each device'
        },
        {
            'step_name': 'Generate Interface Report',
            'step_type': 'code',
            'step_order': 3,
            'enabled': 1,
            'devices': json.dumps([]),
            'config': json.dumps({
                'script': '''# Combine interface status and Netbox data into a comprehensive report
import json
from datetime import datetime

report = {
    'generated_at': datetime.utcnow().isoformat(),
    'validation_passed': context.get('all_devices_validated', False),
    'devices': {}
}

for device_name, device_data in context['devices'].items():
    device_report = {
        'device_name': device_name,
        'platform': device_data.get('platform', 'unknown'),
        'site': device_data.get('site', 'unknown'),
        'interface_summary': {},
        'interfaces': []
    }

    # Get validation results
    validation = context.get('validation_results', {}).get(device_name, {})
    device_report['interface_summary'] = {
        'total_count': validation.get('total_interfaces', 0),
        'up_count': validation.get('up_count', 0),
        'up_interfaces': validation.get('up_interfaces', []),
        'validation_passed': validation.get('validation_passed', False)
    }

    # Get interface status from step 1
    interface_status = device_data.get('interface_status', [])

    # Get Netbox interface data (would need to be populated from API call)
    netbox_interfaces = device_data.get('netbox_interfaces', [])

    # Build interface list with combined data
    for intf_data in interface_status:
        interface_name = intf_data.get('interface', '')

        # Find matching Netbox interface
        netbox_match = None
        if isinstance(netbox_interfaces, list):
            for nb_intf in netbox_interfaces:
                if isinstance(nb_intf, dict) and nb_intf.get('name') == interface_name:
                    netbox_match = nb_intf
                    break

        interface_entry = {
            'name': interface_name,
            'ip_address': intf_data.get('ip_address', 'unassigned'),
            'status': intf_data.get('status', 'unknown'),
            'protocol': intf_data.get('protocol', 'unknown'),
            'netbox_id': netbox_match.get('id') if netbox_match else None,
            'netbox_type': netbox_match.get('type', {}).get('value') if netbox_match else None
        }

        device_report['interfaces'].append(interface_entry)

    report['devices'][device_name] = device_report

# Store final report
context['final_report'] = report

# Print summary
output = f"\\n=== Interface Status Report ===\\n"
output += f"Generated: {report['generated_at']}\\n"
output += f"Overall Validation: {'PASSED' if report['validation_passed'] else 'FAILED'}\\n\\n"

for device_name, device_info in report['devices'].items():
    output += f"Device: {device_name}\\n"
    output += f"  Platform: {device_info['platform']}\\n"
    output += f"  Site: {device_info['site']}\\n"
    output += f"  Interfaces: {device_info['interface_summary']['up_count']}/{device_info['interface_summary']['total_count']} up\\n"
    output += f"  Status: {'✓ PASS' if device_info['interface_summary']['validation_passed'] else '✗ FAIL'}\\n"

    if device_info['interface_summary']['up_interfaces']:
        output += f"  Up Interfaces: {', '.join(device_info['interface_summary']['up_interfaces'])}\\n"
    output += "\\n"

print(output)
print(f"Full report saved to context['final_report']")
''',
                'save_to_variable': 'final_report'
            }),
            'description': 'Combine interface status, validation, and Netbox data into final report'
        }
    ]

    with get_db() as conn:
        cursor = conn.cursor()

        # Generate a unique MOP ID
        import uuid
        mop_id = str(uuid.uuid4())

        # Insert MOP
        cursor.execute('''
            INSERT INTO mops (mop_id, name, description, devices, created_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        ''', (
            mop_id,
            mop_data['name'],
            mop_data['description'],
            mop_data['devices']
        ))

        print(f"Created MOP with ID: {mop_id}")

        # Insert steps
        for step in steps:
            import uuid
            step_id = str(uuid.uuid4())
            cursor.execute('''
                INSERT INTO mop_steps (
                    step_id, mop_id, step_name, step_type, step_order, enabled,
                    devices, config
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                step_id,
                mop_id,
                step['step_name'],
                step['step_type'],
                step['step_order'],
                step['enabled'],
                step['devices'],
                step['config']
            ))
            print(f"  Added step: {step['step_name']}")

        conn.commit()
        print(f"\n✓ Successfully created example MOP: '{mop_data['name']}'")
        print(f"  MOP ID: {mop_id}")
        print(f"  Steps: {len(steps)}")
        print(f"  Devices: bms01-bidev.nae05.gi-nw.viasat.io, dmsp01-cidev.nae05.gi-nw.viasat.io")
        return mop_id

if __name__ == '__main__':
    try:
        mop_id = create_example_mop()
        print(f"\nYou can now view and execute this MOP in the web UI!")
        sys.exit(0)
    except Exception as e:
        print(f"Error creating example MOP: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
