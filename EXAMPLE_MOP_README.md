# Example MOP: Interface Status Report

This is a comprehensive example MOP that demonstrates all the key features of the MOP system including getconfig with TextFSM, code steps for data processing, API calls, and report generation.

## MOP Details

**Name:** Interface Status Report
**MOP ID:** `9ad49b09-8e08-4e29-8c8d-87b5d68c2a3b`
**Devices:**
- bms01-bidev.nae05.gi-nw.viasat.io
- dmsp01-cidev.nae05.gi-nw.viasat.io

## Step-by-Step Breakdown

### Step 1: Get Interface Status
**Type:** `getconfig`
**Command:** `show ip interface brief`
**TextFSM:** Enabled

This step retrieves the interface status from both devices using the `show ip interface brief` command. TextFSM parsing is enabled to convert the raw CLI output into structured data (list of dictionaries).

**Configuration:**
```json
{
  "command": "show ip interface brief",
  "use_textfsm": true,
  "save_to_variable": "interface_status"
}
```

**Expected Output Format (TextFSM parsed):**
```python
[
  {
    "interface": "GigabitEthernet0/0",
    "ip_address": "10.0.1.1",
    "status": "up",
    "protocol": "up"
  },
  ...
]
```

---

### Step 2: Validate Interface Count
**Type:** `code`
**Language:** Python

This step processes the interface data from Step 1 and validates that each device has at least 3 interfaces in an "up/up" state.

**What it does:**
1. Iterates through each device's interface status data
2. Counts interfaces where both `status` and `protocol` are "up"
3. Validates that each device has at least 3 up interfaces
4. Stores validation results in `context['validation_results']`
5. Sets a boolean flag `context['all_devices_validated']`

**Output saved to:** `context['validation_results']`

**Example Output:**
```python
{
  "bms01-bidev.nae05.gi-nw.viasat.io": {
    "total_interfaces": 10,
    "up_interfaces": ["GigabitEthernet0/0", "GigabitEthernet0/1", "GigabitEthernet0/2", "GigabitEthernet0/3"],
    "up_count": 4,
    "validation_passed": True
  },
  "dmsp01-cidev.nae05.gi-nw.viasat.io": {
    "total_interfaces": 8,
    "up_interfaces": ["Ethernet1", "Ethernet2", "Ethernet3"],
    "up_count": 3,
    "validation_passed": True
  }
}
```

---

### Step 3: Get Netbox Interface IDs
**Type:** `api`
**API Resource:** Netbox
**Method:** GET

This step makes API calls to Netbox to retrieve interface information including Netbox IDs for each interface.

**Configuration:**
```json
{
  "resource_id": "netbox",
  "endpoint": "/api/dcim/interfaces/?device={{device_name}}",
  "method": "GET",
  "save_to_variable": "netbox_interfaces"
}
```

**Note:** The `{{device_name}}` variable will be automatically substituted for each device.

**Expected Response:**
```json
{
  "results": [
    {
      "id": 12345,
      "name": "GigabitEthernet0/0",
      "type": {
        "value": "1000base-t",
        "label": "1000BASE-T (1GE)"
      },
      "enabled": true,
      ...
    }
  ]
}
```

---

### Step 4: Generate Interface Report
**Type:** `code`
**Language:** Python

This step combines all the data from previous steps into a comprehensive report structure.

**What it does:**
1. Creates a report structure with timestamp and overall validation status
2. For each device:
   - Combines interface status from Step 1
   - Adds validation results from Step 2
   - Matches Netbox interface IDs from Step 3
3. Generates a formatted text summary
4. Stores the complete report in `context['final_report']`

**Output saved to:** `context['final_report']`

**Example Report Structure:**
```python
{
  "generated_at": "2025-10-26T12:34:56.789012",
  "validation_passed": True,
  "devices": {
    "bms01-bidev.nae05.gi-nw.viasat.io": {
      "device_name": "bms01-bidev.nae05.gi-nw.viasat.io",
      "platform": "cisco_xr",
      "site": "nae05",
      "interface_summary": {
        "total_count": 10,
        "up_count": 4,
        "up_interfaces": ["GigabitEthernet0/0", "GigabitEthernet0/1", ...],
        "validation_passed": True
      },
      "interfaces": [
        {
          "name": "GigabitEthernet0/0",
          "ip_address": "10.0.1.1",
          "status": "up",
          "protocol": "up",
          "netbox_id": 12345,
          "netbox_type": "1000base-t"
        },
        ...
      ]
    }
  }
}
```

**Printed Summary:**
```
=== Interface Status Report ===
Generated: 2025-10-26T12:34:56.789012
Overall Validation: PASSED

Device: bms01-bidev.nae05.gi-nw.viasat.io
  Platform: cisco_xr
  Site: nae05
  Interfaces: 4/10 up
  Status: ✓ PASS
  Up Interfaces: GigabitEthernet0/0, GigabitEthernet0/1, GigabitEthernet0/2, GigabitEthernet0/3

Device: dmsp01-cidev.nae05.gi-nw.viasat.io
  Platform: arista_eos
  Site: nae05
  Interfaces: 3/8 up
  Status: ✓ PASS
  Up Interfaces: Ethernet1, Ethernet2, Ethernet3
```

---

## Key Concepts Demonstrated

### 1. **Variable Substitution**
- Device-specific variables like `{{device_name}}` are automatically substituted in API endpoints

### 2. **Data Persistence Between Steps**
- Data from one step is available to subsequent steps via the `context` dictionary
- Device-specific data is stored in `context['devices'][device_name]`
- Global variables can be stored directly in `context`

### 3. **TextFSM Parsing**
- Raw CLI output is automatically parsed into structured data when `use_textfsm: true`
- Makes it easy to work with CLI output in code steps

### 4. **Code Step Capabilities**
- Full Python scripting with access to all data from previous steps
- Can process, validate, and transform data
- Can store results back to context for use by later steps

### 5. **API Integration**
- Seamless integration with external APIs (Netbox in this example)
- Variable substitution for dynamic API calls
- Response data is automatically stored in context

### 6. **Parallel Device Execution**
- When multiple devices are specified in a step, they execute in parallel
- Each device's data is tracked separately in the context

---

## How to Run This MOP

1. Navigate to the **MOPs** page in the UI
2. Find "Interface Status Report" in the list
3. Click **Execute**
4. Monitor real-time progress as each step completes
5. View detailed results including the final report

## Viewing Results

After execution, you can view:
- Per-device interface status from Step 1
- Validation results from Step 2
- Netbox interface data from Step 3
- Complete combined report from Step 4

All execution results are stored in the MOP execution history and can be reviewed later.

---

## Customization Ideas

You can customize this MOP by:

1. **Changing the validation threshold:** Modify Step 2 to require more/fewer up interfaces
2. **Adding more commands:** Add additional getconfig steps for more data collection
3. **Enhanced reporting:** Modify Step 4 to include more fields or different formatting
4. **Export functionality:** Add a step to export the report to a file or external system
5. **Alerting:** Add conditional logic to send alerts if validation fails

---

## Creating Your Own MOPs

Use this example as a template to create your own MOPs:

1. Start with data collection (getconfig/API steps)
2. Add validation logic (code steps)
3. Enrich with external data sources (API steps)
4. Generate reports or take actions (code/API steps)

Remember: Each step's output is available to all subsequent steps via the `context` dictionary!
