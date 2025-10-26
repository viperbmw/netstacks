// Network Map Visualization using Vis.js
let network = null;
let nodes = null;
let edges = null;
let allDevices = [];
let currentNodeSize = 25;

// Color mapping for device types
const deviceColors = {
    'cisco_ios': '#4A90E2',
    'cisco_xe': '#4A90E2',
    'cisco_nxos': '#50C878',
    'arista_eos': '#FF6B6B',
    'juniper_junos': '#9B59B6',
    'linux': '#F39C12',
    'default': '#95A5A6'
};

// Initialize the network visualization
function initNetwork() {
    const container = document.getElementById('network-container');

    if (!container) {
        console.error('Network container element not found!');
        return;
    }

    if (typeof vis === 'undefined') {
        console.error('Vis.js library not loaded!');
        return;
    }

    // Create empty datasets
    nodes = new vis.DataSet([]);
    edges = new vis.DataSet([]);

    const data = {
        nodes: nodes,
        edges: edges
    };

    const options = {
        nodes: {
            shape: 'dot',
            size: currentNodeSize,
            font: {
                size: 16,
                color: '#ffffff',
                background: 'rgba(0,0,0,0.6)',
                strokeWidth: 4,
                strokeColor: '#000000'
            },
            borderWidth: 3,
            borderWidthSelected: 5,
            shadow: {
                enabled: true,
                color: 'rgba(0,0,0,0.3)',
                size: 10,
                x: 2,
                y: 2
            }
        },
        edges: {
            width: 3,
            color: {
                color: '#97C2FC',
                highlight: '#FFA500',
                hover: '#FFA500'
            },
            smooth: {
                type: 'continuous',
                roundness: 0.5
            },
            shadow: {
                enabled: true,
                color: 'rgba(0,0,0,0.2)',
                size: 5,
                x: 1,
                y: 1
            }
        },
        physics: {
            enabled: true,
            stabilization: {
                enabled: true,
                iterations: 200,
                updateInterval: 25
            },
            barnesHut: {
                gravitationalConstant: -35000,
                centralGravity: 0.4,
                springLength: 200,
                springConstant: 0.05,
                damping: 0.1,
                avoidOverlap: 0.8
            }
        },
        interaction: {
            hover: true,
            tooltipDelay: 100,
            hideEdgesOnDrag: true,
            navigationButtons: true,
            keyboard: {
                enabled: true,
                bindToWindow: false
            },
            zoomView: true,
            dragView: true
        },
        layout: {
            improvedLayout: true,
            randomSeed: 42
        }
    };

    try {
        network = new vis.Network(container, data, options);
    } catch (error) {
        console.error('Error creating Vis.js network:', error);
        return;
    }

    // Event handlers
    network.on('click', function(params) {
        if (params.nodes.length > 0) {
            const nodeId = params.nodes[0];
            showDeviceInfo(nodeId);
        } else {
            clearDeviceInfo();
        }
    });

    network.on('doubleClick', function(params) {
        if (params.nodes.length > 0) {
            const nodeId = params.nodes[0];
            // Navigate to device page or deploy config
            window.location.href = '/devices';
        }
    });

    network.on('hoverNode', function(params) {
        const node = nodes.get(params.node);
        if (node && node.title) {
            // Vis.js will show the title as tooltip automatically
        }
    });
}

// Load devices from API (using existing /api/devices with filters and cache)
async function loadDevices() {
    // Load settings to get NetBox filters
    let filters = [];
    try {
        const settingsResponse = await $.ajax({
            url: '/api/settings',
            method: 'GET'
        });
        if (settingsResponse.success && settingsResponse.settings) {
            filters = settingsResponse.settings.netbox_filters || [];
        }
    } catch (e) {
        console.error('Error loading settings:', e);
    }

    // Make POST request with filters (like other pages do)
    $.ajax({
        url: '/api/devices',
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({ filters: filters }),
        success: function(response) {
            if (response.success) {
                // Transform devices to network map format
                allDevices = response.devices.map((device, index) => {
                    const source = device.source || 'netbox';
                    const deviceType = device.device_type || 'unknown';

                    return {
                        id: `${source}-${index}`,
                        name: device.name,
                        type: deviceType,
                        source: source,
                        ip: device.primary_ip || device.primary_ip4,
                        site: device.site,
                        status: device.status
                    };
                });

                // Show cache status badge
                if (response.cached) {
                    $('#cache-status-badge').show();
                } else {
                    $('#cache-status-badge').hide();
                }

                // Warning for large datasets
                if (allDevices.length > 500) {
                    $('#network-container').html(`
                        <div class="alert alert-warning m-3" role="alert">
                            <i class="fas fa-exclamation-triangle"></i>
                            <strong>Large Dataset Warning:</strong> You have ${allDevices.length} devices.
                            Rendering this many nodes may cause performance issues.
                            <br><br>
                            <strong>Recommendations:</strong>
                            <ul>
                                <li>Use the search filter below to narrow down devices</li>
                                <li>Add NetBox filters in Settings page to reduce device count</li>
                                <li>Filter by site, role, or tag in NetBox settings</li>
                            </ul>
                            <p class="mt-2 mb-2 small">
                                ${response.cached ? '<span class="badge bg-info">Using cached devices</span>' : ''}
                                ${filters.length > 0 ? `<span class="badge bg-secondary ms-2">${filters.length} filter(s) applied</span>` : '<span class="badge bg-warning ms-2">No filters applied</span>'}
                            </p>
                            <button class="btn btn-primary btn-sm mt-2" onclick="forceRenderNetwork()">
                                Render Anyway (may be slow)
                            </button>
                            <a href="/settings" class="btn btn-secondary btn-sm mt-2">
                                <i class="fas fa-cog"></i> Configure Filters
                            </a>
                        </div>
                    `);
                } else {
                    renderNetwork(allDevices);
                    updateDeviceCount(allDevices.length);
                    // Fetch real connections from NetBox
                    loadConnections(allDevices);
                }
            } else {
                showError('Failed to load devices: ' + (response.error || 'Unknown error'));
            }
        },
        error: function(xhr, status, error) {
            console.error('Error loading devices:', error, xhr.responseText);
            showError('Error loading devices: ' + error);
        }
    });
}

// Force render for large datasets
function forceRenderNetwork() {
    renderNetwork(allDevices);
    updateDeviceCount(allDevices.length);
}

// Render network with devices
function renderNetwork(devices) {
    nodes.clear();
    edges.clear();

    const showManual = $('#show-manual-devices').is(':checked');
    const showNetbox = $('#show-netbox-devices').is(':checked');
    const filterText = $('#filter-input').val().toLowerCase();

    // Filter devices
    const filteredDevices = devices.filter(device => {
        // Handle both 'manual' and 'netbox' sources
        const source = (device.source || 'netbox').toLowerCase();

        if (!showManual && source === 'manual') return false;
        if (!showNetbox && source === 'netbox') return false;
        if (filterText && !device.name.toLowerCase().includes(filterText)) return false;
        return true;
    });

    if (!network) {
        console.error('Network object is null! Cannot render devices.');
        return;
    }

    // Add nodes for each device
    filteredDevices.forEach(device => {
        const deviceType = device.type || 'default';
        const color = deviceColors[deviceType] || deviceColors['default'];
        const icon = device.source === 'netbox' ? '\uf233' : '\uf109'; // FontAwesome unicode

        nodes.add({
            id: device.id,
            label: $('#show-labels').is(':checked') ? device.name : '',
            title: createTooltip(device),
            color: {
                background: color,
                border: darkenColor(color, 30),
                highlight: {
                    background: lightenColor(color, 15),
                    border: darkenColor(color, 20)
                },
                hover: {
                    background: lightenColor(color, 10),
                    border: darkenColor(color, 20)
                }
            },
            font: {
                color: '#ffffff',
                size: 13,
                face: 'Arial, sans-serif',
                background: 'rgba(0,0,0,0.7)',
                strokeWidth: 3,
                strokeColor: '#000000'
            },
            size: currentNodeSize,
            borderWidth: 3,
            deviceData: device
        });
    });

    // Fit the network view
    setTimeout(() => {
        network.fit({
            animation: {
                duration: 1000,
                easingFunction: 'easeInOutQuad'
            }
        });
    }, 500);
}

// Load real connections from NetBox
function loadConnections(devices) {
    // Extract device names
    const deviceNames = devices.map(d => d.name);

    if (deviceNames.length === 0) {
        return;
    }

    // Fetch connections from API
    $.ajax({
        url: '/api/network-connections',
        method: 'POST',
        contentType: 'application/json',
        dataType: 'json',
        data: JSON.stringify({ device_names: deviceNames }),
        success: function(response) {
            if (response.success && response.connections) {
                renderConnections(response.connections, devices);
            }
        },
        error: function(xhr, status, error) {
            console.error('Error loading connections:', error);
            // Try to parse and show the response anyway
            if (xhr && xhr.responseText) {
                try {
                    const parsed = JSON.parse(xhr.responseText);
                    if (parsed.success && parsed.connections) {
                        renderConnections(parsed.connections, devices);
                    }
                } catch (e) {
                    console.error('Could not parse response:', e);
                }
            }
        }
    });
}

// Render connections on the network map
function renderConnections(connections, devices) {
    // Create a map of device name to device ID for quick lookup
    const deviceNameToId = {};
    devices.forEach(device => {
        deviceNameToId[device.name] = device.id;
    });

    // Add edges for each connection
    connections.forEach((conn, index) => {
        const sourceId = deviceNameToId[conn.source];
        const targetId = deviceNameToId[conn.target];

        if (sourceId && targetId) {
            const title = `${conn.source_interface || 'Unknown'} <-> ${conn.target_interface || 'Unknown'}`;

            edges.add({
                id: `edge-${index}`,
                from: sourceId,
                to: targetId,
                title: title,
                width: 3,
                color: {
                    color: '#97C2FC',
                    highlight: '#FFA500',
                    hover: '#FFA500'
                },
                smooth: {
                    type: 'continuous',
                    roundness: 0.5
                }
            });
        }
    });
}

// Create tooltip for device
function createTooltip(device) {
    let tooltip = `<strong>${device.name}</strong><br>`;
    tooltip += `Type: ${device.type || 'Unknown'}<br>`;
    tooltip += `Source: ${device.source}<br>`;
    if (device.ip) tooltip += `IP: ${device.ip}<br>`;
    return tooltip;
}

// Show device info in side panel
function showDeviceInfo(nodeId) {
    const node = nodes.get(nodeId);
    if (!node || !node.deviceData) return;

    const device = node.deviceData;
    let html = `
        <div class="device-details">
            <h6 class="mb-3">${device.name}</h6>
            <table class="table table-sm">
                <tr>
                    <th>Type:</th>
                    <td>${device.type || 'Unknown'}</td>
                </tr>
                <tr>
                    <th>Source:</th>
                    <td><span class="badge bg-secondary">${device.source}</span></td>
                </tr>
    `;

    if (device.ip) {
        html += `
                <tr>
                    <th>IP:</th>
                    <td>${device.ip}</td>
                </tr>
        `;
    }

    if (device.port) {
        html += `
                <tr>
                    <th>Port:</th>
                    <td>${device.port}</td>
                </tr>
        `;
    }

    html += `
            </table>
            <div class="d-grid gap-2">
                <a href="/deploy?device=${encodeURIComponent(device.name)}" class="btn btn-sm btn-primary">
                    <i class="fas fa-rocket"></i> Deploy Config
                </a>
                <button class="btn btn-sm btn-outline-secondary" onclick="focusOnDevice('${nodeId}')">
                    <i class="fas fa-crosshairs"></i> Focus
                </button>
            </div>
        </div>
    `;

    $('#device-info-panel').html(html);
}

// Clear device info panel
function clearDeviceInfo() {
    $('#device-info-panel').html('<p class="text-muted text-center">Click a device to view details</p>');
}

// Focus on specific device
function focusOnDevice(nodeId) {
    network.focus(nodeId, {
        scale: 1.5,
        animation: {
            duration: 1000,
            easingFunction: 'easeInOutQuad'
        }
    });
    network.selectNodes([nodeId]);
}

// Update device count badge
function updateDeviceCount(count) {
    $('#device-count-badge').text(`${count} device${count !== 1 ? 's' : ''}`);
}

// Show error message
function showError(message) {
    const container = document.getElementById('network-container');
    container.innerHTML = `
        <div class="alert alert-danger m-3" role="alert">
            <i class="fas fa-exclamation-triangle"></i> ${message}
        </div>
    `;
}

// Utility: Darken color
function darkenColor(hex, percent) {
    const num = parseInt(hex.replace('#', ''), 16);
    const amt = Math.round(2.55 * percent);
    const R = (num >> 16) - amt;
    const G = (num >> 8 & 0x00FF) - amt;
    const B = (num & 0x0000FF) - amt;
    return '#' + (0x1000000 + (R < 255 ? R < 1 ? 0 : R : 255) * 0x10000 +
        (G < 255 ? G < 1 ? 0 : G : 255) * 0x100 +
        (B < 255 ? B < 1 ? 0 : B : 255))
        .toString(16).slice(1);
}

// Utility: Lighten color
function lightenColor(hex, percent) {
    const num = parseInt(hex.replace('#', ''), 16);
    const amt = Math.round(2.55 * percent);
    const R = (num >> 16) + amt;
    const G = (num >> 8 & 0x00FF) + amt;
    const B = (num & 0x0000FF) + amt;
    return '#' + (0x1000000 + (R < 255 ? R < 1 ? 0 : R : 255) * 0x10000 +
        (G < 255 ? G < 1 ? 0 : G : 255) * 0x100 +
        (B < 255 ? B < 1 ? 0 : B : 255))
        .toString(16).slice(1);
}

// Event Handlers
$(document).ready(function() {
    // Initialize network
    initNetwork();

    // Load devices
    loadDevices();

    // Layout change
    $('#layout-select').change(function() {
        const layout = $(this).val();

        if (layout === 'hierarchical') {
            network.setOptions({
                layout: {
                    hierarchical: {
                        enabled: true,
                        direction: 'UD',
                        sortMethod: 'directed',
                        levelSeparation: 150,
                        nodeSpacing: 150
                    }
                },
                physics: {
                    enabled: false
                }
            });
        } else if (layout === 'random') {
            network.setOptions({
                layout: {
                    hierarchical: {
                        enabled: false
                    },
                    randomSeed: Math.random()
                },
                physics: {
                    enabled: false
                }
            });
        } else {
            network.setOptions({
                layout: {
                    hierarchical: {
                        enabled: false
                    }
                },
                physics: {
                    enabled: true
                }
            });
        }
    });

    // Node size slider
    $('#node-size-slider').on('input', function() {
        currentNodeSize = parseInt($(this).val());
        nodes.forEach(node => {
            nodes.update({id: node.id, size: currentNodeSize});
        });
    });

    // Refresh button
    $('#refresh-btn').click(function() {
        $(this).find('i').addClass('fa-spin');
        loadDevices();
        setTimeout(() => {
            $(this).find('i').removeClass('fa-spin');
        }, 1000);
    });

    // Fit view button
    $('#fit-btn').click(function() {
        network.fit({
            animation: {
                duration: 1000,
                easingFunction: 'easeInOutQuad'
            }
        });
    });

    // Show/hide labels
    $('#show-labels').change(function() {
        const showLabels = $(this).is(':checked');
        nodes.forEach(node => {
            const label = showLabels ? node.deviceData.name : '';
            nodes.update({id: node.id, label: label});
        });
    });

    // Enable/disable physics
    $('#physics-enabled').change(function() {
        const enabled = $(this).is(':checked');
        network.setOptions({
            physics: {
                enabled: enabled
            }
        });
    });

    // Filter checkboxes
    $('#show-manual-devices, #show-netbox-devices').change(function() {
        renderNetwork(allDevices);
    });

    // Filter input
    let filterTimeout;
    $('#filter-input').on('input', function() {
        clearTimeout(filterTimeout);
        filterTimeout = setTimeout(() => {
            renderNetwork(allDevices);
        }, 300);
    });
});
