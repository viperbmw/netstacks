#!/usr/bin/env python3
"""
Test script for YAML workflow engine

Run this to test workflows without the web UI:
    python test_workflow.py workflows/example_simple.yaml
"""

import sys
import json
from workflow_engine import WorkflowEngine

def test_workflow(workflow_file):
    """Test a workflow file"""
    print(f"\n{'='*60}")
    print(f"Testing Workflow: {workflow_file}")
    print(f"{'='*60}\n")

    # Create sample context (simulating device data)
    context = {
        'devices': {
            'bms01-bidev.nae05.gi-nw.viasat.io': {
                'name': 'bms01-bidev.nae05.gi-nw.viasat.io',
                'ip_address': '10.0.1.1',
                'platform': 'cisco_xr',
                'site': 'nae05',
                'bgp_neighbor_count': 4
            },
            'dmsp01-cidev.nae05.gi-nw.viasat.io': {
                'name': 'dmsp01-cidev.nae05.gi-nw.viasat.io',
                'ip_address': '10.0.1.2',
                'platform': 'arista_eos',
                'site': 'nae05',
                'bgp_neighbor_count': 4
            },
            'router1': {
                'name': 'router1',
                'ip_address': '10.0.2.1',
                'bgp_neighbor_count': 2
            },
            'router2': {
                'name': 'router2',
                'ip_address': '10.0.2.2',
                'bgp_neighbor_count': 2
            }
        }
    }

    # Execute workflow
    engine = WorkflowEngine(workflow_file, context)
    result = engine.execute()

    # Print results
    print(f"\nWorkflow Status: {result['status'].upper()}")
    print(f"\n{'='*60}")
    print("Execution Log:")
    print(f"{'='*60}\n")

    for log_entry in result.get('execution_log', []):
        status_icon = "✓" if log_entry['status'] == 'success' else "✗"
        print(f"{status_icon} Step {log_entry['step_index'] + 1}: {log_entry['step']}")
        print(f"  Status: {log_entry['status']}")
        if log_entry.get('message'):
            print(f"  Message: {log_entry['message']}")
        print()

    print(f"{'='*60}")
    print(f"Final Result: {result.get('message', 'No message')}")
    print(f"{'='*60}\n")

    # Print full result as JSON (for debugging)
    if '--verbose' in sys.argv:
        print("\nFull Result (JSON):")
        print(json.dumps(result, indent=2, default=str))

    return result


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python test_workflow.py <workflow.yaml> [--verbose]")
        print("\nExample workflows:")
        print("  python test_workflow.py workflows/example_simple.yaml")
        print("  python test_workflow.py workflows/example_maintenance.yaml")
        print("  python test_workflow.py workflows/example_custom_python.yaml")
        sys.exit(1)

    workflow_file = sys.argv[1]
    result = test_workflow(workflow_file)

    # Exit with appropriate code
    sys.exit(0 if result['status'] == 'completed' else 1)
