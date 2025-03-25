// Host view JavaScript functionality

// Store host ID from template for API calls
const HOST_ID = document.getElementById('host-data').dataset.hostId;

// Service control functions
function loadServices() {
    document.getElementById('services-loading').style.display = 'block';
    document.getElementById('services-table').style.display = 'none';
    document.getElementById('services-error').style.display = 'none';
    document.getElementById('no-services').style.display = 'none';
    
    fetch(`/api/hosts/${HOST_ID}/services`)
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! Status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            // Hide loading indicator
            document.getElementById('services-loading').style.display = 'none';
            
            // Check for error
            if (data.error) {
                document.getElementById('services-error').textContent = 'Error: ' + data.error;
                document.getElementById('services-error').style.display = 'block';
                return;
            }
            
            // Check if empty
            if (!data || data.length === 0) {
                document.getElementById('no-services').style.display = 'block';
                return;
            }
            
            // Show table and populate data
            document.getElementById('services-table').style.display = 'table';
            
            const servicesList = document.getElementById('services-list');
            servicesList.innerHTML = '';
            
            data.forEach(service => {
                const row = document.createElement('tr');
                row.className = service.running ? 'service-row-running' : 'service-row-stopped';
                row.dataset.serviceName = service.name;  // Store service name in dataset
                
                // Service name cell
                const nameCell = document.createElement('td');
                nameCell.textContent = service.name;
                row.appendChild(nameCell);
                
                // Status cell
                const statusCell = document.createElement('td');
                const statusIndicator = document.createElement('span');
                statusIndicator.className = 'service-status ' + 
                                          (service.running ? 'service-status-running' : 'service-status-stopped');
                statusCell.appendChild(statusIndicator);
                statusCell.appendChild(document.createTextNode(
                    service.running ? 'Running' : 'Stopped'
                ));
                row.appendChild(statusCell);
                
                // Boot cell
                const bootCell = document.createElement('td');
                bootCell.textContent = service.enabled ? 'Enabled' : 'Disabled';
                row.appendChild(bootCell);
                
                // Actions cell
                const actionsCell = document.createElement('td');
                
                // Start/Stop button
                const toggleBtn = document.createElement('button');
                toggleBtn.className = 'button ' + (service.running ? 'stop-btn' : '');
                toggleBtn.textContent = service.running ? 'Stop' : 'Start';
                toggleBtn.onclick = function() {
                    controlService(service.name, service.running ? 'stop' : 'start', toggleBtn);
                };
                actionsCell.appendChild(toggleBtn);
                
                // Enable/Disable button
                const bootBtn = document.createElement('button');
                bootBtn.className = 'button';
                bootBtn.textContent = service.enabled ? 'Disable' : 'Enable';
                bootBtn.style.marginLeft = '5px';
                bootBtn.onclick = function() {
                    controlService(service.name, service.enabled ? 'disable' : 'enable', bootBtn);
                };
                actionsCell.appendChild(bootBtn);
                
                // Restart button (only for running services)
                if (service.running) {
                    const restartBtn = document.createElement('button');
                    restartBtn.className = 'button reload-btn';
                    restartBtn.textContent = 'Restart';
                    restartBtn.style.marginLeft = '5px';
                    restartBtn.onclick = function() {
                        controlService(service.name, 'restart', restartBtn);
                    };
                    actionsCell.appendChild(restartBtn);
                }
                
                // Add a details/metadata button
                if (service.running) {  // Only show for running services
                    const detailsBtn = document.createElement('button');
                    detailsBtn.className = 'button';
                    detailsBtn.textContent = 'Details';
                    detailsBtn.style.marginLeft = '5px';
                    detailsBtn.style.backgroundColor = '#17a2b8';
                    detailsBtn.onclick = function() {
                        toggleMetadata(service.name, row);
                    };
                    actionsCell.appendChild(detailsBtn);
                }
                
                row.appendChild(actionsCell);
                
                // Create a row for metadata (initially hidden)
                const metadataRow = document.createElement('tr');
                metadataRow.className = 'metadata-row';
                metadataRow.style.display = 'none';  // Initially hidden
                
                const metadataCell = document.createElement('td');
                metadataCell.colSpan = 4;
                metadataCell.innerHTML = '<div class="metadata-panel" id="metadata-' + service.name + '"><div class="loading-spinner"></div> Loading metadata...</div>';
                metadataRow.appendChild(metadataCell);
                
                // Add both rows
                servicesList.appendChild(row);
                servicesList.appendChild(metadataRow);
            });
        })
        .catch(error => {
            console.error('Error fetching services:', error);
            document.getElementById('services-loading').style.display = 'none';
            document.getElementById('services-error').textContent = 'Failed to load services: ' + error.message;
            document.getElementById('services-error').style.display = 'block';
        });
}

function controlService(serviceName, action, button) {
    // Disable button and show loading state
    const originalText = button.textContent;
    button.disabled = true;
    button.textContent = 'Working...';
    
    fetch(`/api/hosts/${HOST_ID}/services/${serviceName}/${action}`, {
        method: 'POST'
    })
    .then(response => response.json())
    .then(data => {
        // Restore button state
        button.disabled = false;
        button.textContent = originalText;
        
        if (data.success) {
            // Reload services to show updated status
            loadServices();
        } else {
            alert(`Failed to ${action} service: ${data.message}`);
        }
    })
    .catch(error => {
        console.error(`Error ${action} service:`, error);
        button.disabled = false;
        button.textContent = originalText;
        alert(`Error: ${error.message}`);
    });
}

function testConnection() {
    const button = document.querySelector('.reload-btn');
    const originalText = button.textContent;
    button.disabled = true;
    button.textContent = 'Testing...';
    
    fetch(`/api/hosts/${HOST_ID}/test`, {
        method: 'POST'
    })
    .then(response => response.json())
    .then(data => {
        button.disabled = false;
        button.textContent = originalText;
        
        if (data.success) {
            alert('Connection successful!');
            location.reload(); // Refresh the page to update status
        } else {
            alert('Connection failed: ' + data.message);
        }
    })
    .catch(error => {
        button.disabled = false;
        button.textContent = originalText;
        alert('Error: ' + error.message);
    });
}

// Function to toggle metadata visibility
function toggleMetadata(serviceName, row) {
    const metadataRow = row.nextElementSibling;
    const isVisible = metadataRow.style.display === 'table-row';
    
    // Toggle visibility
    metadataRow.style.display = isVisible ? 'none' : 'table-row';
    
    // If showing and not loaded yet, fetch metadata
    if (!isVisible) {
        const metadataPanel = document.getElementById('metadata-' + serviceName);
        console.log("Showing metadata panel for", serviceName);
        
        // Make the panel itself visible
        metadataPanel.style.display = 'block';
        
        // Only load if not already loaded
        if (metadataPanel.querySelector('.loading-spinner')) {
            loadMetadata(serviceName, metadataPanel);
        }
    }
}

// Function to load service metadata with resource information
function loadMetadata(serviceName, panel) {
    console.log("Loading metadata for", serviceName);
    fetch(`/api/hosts/${HOST_ID}/services/${serviceName}/metadata`)
        .then(response => {
            console.log("Metadata response status:", response.status);
            if (!response.ok) {
                throw new Error(`HTTP error! Status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            console.log("Received metadata:", data);
            // Clear loading indicator
            panel.innerHTML = '';
            
            // Check for error
            if (data.error) {
                panel.innerHTML = '<div class="error-message">Error: ' + data.error + '</div>';
                return;
            }
            
            // Create metadata section
            const serviceTitle = document.createElement('div');
            serviceTitle.className = 'metadata-title';
            serviceTitle.textContent = 'Service: ' + serviceName;
            panel.appendChild(serviceTitle);
            
            // 1. RESOURCE INFORMATION SECTION - Add this first as it's most important
            if (data.resources) {
                addResourceSection(panel, data.resources);
            }
            
            // 2. SERVICE METADATA SECTION
            if (data.metadata && Object.keys(data.metadata).length > 0) {
                const metadataTitle = document.createElement('h4');
                metadataTitle.textContent = 'Service Metadata';
                metadataTitle.style.marginTop = '20px';
                panel.appendChild(metadataTitle);
                
                const metadataTable = document.createElement('table');
                metadataTable.className = 'metadata-table';
                
                // Sort keys alphabetically for better display
                const sortedKeys = Object.keys(data.metadata).sort();
                
                for (const key of sortedKeys) {
                    const value = data.metadata[key];
                    const row = metadataTable.insertRow();
                    const keyCell = row.insertCell(0);
                    const valueCell = row.insertCell(1);
                    
                    keyCell.textContent = key;
                    valueCell.textContent = value;
                }
                
                panel.appendChild(metadataTable);
            } else {
                const noMetadata = document.createElement('p');
                noMetadata.textContent = 'No custom metadata found for this service.';
                panel.appendChild(noMetadata);
            }
            
            // 3. CONFIGURATION SECTIONS
            if (data.config) {
                addCollapsibleSection(panel, 'Unit Configuration', data.config.Unit);
                addCollapsibleSection(panel, 'Service Configuration', data.config.Service);
            }
            
            // 4. LOGS SECTION (at the end)
            const logsSection = document.createElement('div');
            logsSection.id = 'logs-container-' + serviceName;
            logsSection.style.marginTop = '20px';
            
            const logsTitle = document.createElement('h4');
            logsTitle.textContent = 'Service Logs';
            logsSection.appendChild(logsTitle);
            
            const viewLogsBtn = document.createElement('button');
            viewLogsBtn.className = 'button reload-btn';
            viewLogsBtn.textContent = 'View Logs';
            viewLogsBtn.onclick = function() {
                loadLogs(serviceName, logsSection);
                viewLogsBtn.style.display = 'none';
            };
            logsSection.appendChild(viewLogsBtn);
            
            panel.appendChild(logsSection);
        })
        .catch(error => {
            console.error('Error fetching metadata:', error);
            panel.innerHTML = '<div class="error-message">Failed to load metadata: ' + error.message + '</div>';
        });
}

// Function to add resource section
function addResourceSection(panel, resources) {
    const resourceTitle = document.createElement('h4');
    resourceTitle.textContent = 'Resource Usage';
    panel.appendChild(resourceTitle);
    
    const resourceTable = document.createElement('table');
    resourceTable.className = 'metadata-table';
    
    // PID
    if (resources.pid) {
        const pidRow = resourceTable.insertRow();
        const pidKeyCell = pidRow.insertCell(0);
        const pidValueCell = pidRow.insertCell(1);
        pidKeyCell.textContent = 'PID';
        pidValueCell.textContent = resources.pid;
    }
    
    // CPU Usage
    if (resources.cpu_usage) {
        const cpuRow = resourceTable.insertRow();
        const cpuKeyCell = cpuRow.insertCell(0);
        const cpuValueCell = cpuRow.insertCell(1);
        cpuKeyCell.textContent = 'CPU Usage';
        cpuValueCell.textContent = resources.cpu_usage;
    }
    
    // Memory Usage (Current)
    if (resources.memory && resources.memory.current) {
        const memCurrentRow = resourceTable.insertRow();
        const memCurrentKeyCell = memCurrentRow.insertCell(0);
        const memCurrentValueCell = memCurrentRow.insertCell(1);
        memCurrentKeyCell.textContent = 'Memory (Current)';
        memCurrentValueCell.textContent = resources.memory.current;
    }
    
    // Memory Usage (Peak)
    if (resources.memory && resources.memory.peak) {
        const memPeakRow = resourceTable.insertRow();
        const memPeakKeyCell = memPeakRow.insertCell(0);
        const memPeakValueCell = memPeakRow.insertCell(1);
        memPeakKeyCell.textContent = 'Memory (Peak)';
        memPeakValueCell.textContent = resources.memory.peak;
    }
    
    // Uptime and Started
    if (resources.uptime) {
        const uptimeRow = resourceTable.insertRow();
        const uptimeKeyCell = uptimeRow.insertCell(0);
        const uptimeValueCell = uptimeRow.insertCell(1);
        uptimeKeyCell.textContent = 'Uptime';
        
        let uptimeText = resources.uptime;
        if (resources.started_at) {
            uptimeText += ` (since ${resources.started_at})`;
        }
        
        uptimeValueCell.textContent = uptimeText;
    }
    
    panel.appendChild(resourceTable);
}

// Enhanced function to load and display service logs with debug
function loadLogs(serviceName, container, page = 1) {
    // Clear previous content and show loading indicator
    container.innerHTML = '<div class="loading-spinner"></div> Loading logs...';
    
    // Determine per_page parameter (default to 50 for a consistent page size)
    const per_page = 50;
    
    // Always include pagination parameters in the URL
    let url = `/api/hosts/${HOST_ID}/services/${serviceName}/logs?per_page=${per_page}&page=${page}`;
    
    console.log(`Fetching logs with URL: ${url}`);
    
    fetch(url)
        .then(response => {
            console.log("Logs response status:", response.status);
            if (!response.ok) {
                throw new Error(`HTTP error! Status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            // Enhanced debug info
            console.log("Received logs data:", data);
            
            // Debug pagination specifically
            const pagination = data.pagination || null;
            console.log("Pagination data:", pagination);
            if (pagination) {
                console.log(`Pagination details: page=${pagination.page}, total_pages=${pagination.total_pages}, has_prev=${pagination.has_prev}, has_next=${pagination.has_next}`);
            } else {
                console.log("No pagination data received from server");
            }
            
            // Clear container
            container.innerHTML = '';
            
            // Check for API error
            if (data.error) {
                container.innerHTML = 
                    `<div class="error-message">Error: ${data.error}</div>
                     <div class="info-message">Command attempted: ${data.command || "Unknown"}</div>`;
                return;
            }
            
            const logs = data.logs || [];
            
            if (logs.length > 0) {
                const logsDiv = document.createElement('div');
                logsDiv.className = 'logs-output';
                
                // Add log count and pagination information
                const logInfoBar = document.createElement('div');
                logInfoBar.style.display = 'flex';
                logInfoBar.style.justifyContent = 'space-between';
                logInfoBar.style.marginBottom = '10px';
                logInfoBar.style.fontSize = '14px';
                
                // Left side: log count
                const logCount = document.createElement('div');
                if (pagination) {
                    // For paginated view, show total logs and current page
                    const startLog = (pagination.page-1)*pagination.per_page+1;
                    const endLog = Math.min(pagination.page*pagination.per_page, pagination.total_logs);
                    logCount.innerHTML = `<strong>Showing logs ${startLog}-${endLog} of ${pagination.total_logs}</strong>`;
                } else {
                    // For standard view, just show count
                    logCount.innerHTML = `<strong>Showing ${logs.length} log entries</strong>`;
                }
                logInfoBar.appendChild(logCount);
                
                // Right side: pagination info if available
                if (pagination) {
                    const pageInfo = document.createElement('div');
                    pageInfo.innerHTML = `<strong>Page ${pagination.page} of ${pagination.total_pages}</strong>`;
                    logInfoBar.appendChild(pageInfo);
                }
                
                logsDiv.appendChild(logInfoBar);
                
                // Add horizontal divider
                const divider = document.createElement('hr');
                divider.style.margin = '5px 0';
                divider.style.border = '0';
                divider.style.borderTop = '1px solid #ddd';
                logsDiv.appendChild(divider);
                
                // Add logs content
                logs.forEach(log => {
                    const logLine = document.createElement('div');
                    
                    // Handle different log formats
                    if (log.timestamp && log.message) {
                        const timestampSpan = document.createElement('span');
                        timestampSpan.style.color = '#666';
                        timestampSpan.textContent = `[${log.timestamp}] `;
                        
                        logLine.appendChild(timestampSpan);
                        logLine.appendChild(document.createTextNode(log.message));
                    } else if (log.raw) {
                        logLine.textContent = log.raw;
                    } else {
                        // Fallback for unknown format
                        logLine.textContent = JSON.stringify(log);
                    }
                    
                    logsDiv.appendChild(logLine);
                });
                
                container.appendChild(logsDiv);
                
                // Create pagination controls container
                const paginationContainer = document.createElement('div');
                paginationContainer.className = 'pagination-controls';
                paginationContainer.style.marginTop = '15px';
                paginationContainer.style.textAlign = 'center';
                
                // Debug pagination rendering condition
                console.log(`Should show pagination? ${!!(pagination && pagination.total_pages > 1)}`);
                console.log(`pagination.total_pages = ${pagination ? pagination.total_pages : 'undefined'}`);
                
                if (pagination && pagination.total_pages > 1) {
                    console.log("Adding pagination controls");
                    
                    // Add previous button if not on first page
                    if (pagination.has_prev) {
                        console.log("Adding Previous button");
                        const prevButton = document.createElement('button');
                        prevButton.className = 'button';
                        prevButton.textContent = '← Previous';
                        prevButton.onclick = function() {
                            loadLogs(serviceName, container, pagination.page - 1);
                        };
                        paginationContainer.appendChild(prevButton);
                    }
                    
                    // Add page indicator
                    const pageIndicator = document.createElement('span');
                    pageIndicator.className = 'page-indicator'; // Add a class for easier debugging
                    pageIndicator.style.margin = '0 15px';
                    pageIndicator.style.display = 'inline-block';
                    pageIndicator.style.verticalAlign = 'middle';
                    pageIndicator.style.fontSize = '16px';
                    pageIndicator.textContent = `Page ${pagination.page} of ${pagination.total_pages}`;
                    paginationContainer.appendChild(pageIndicator);
                    
                    // Add next button if not on last page
                    if (pagination.has_next) {
                        console.log("Adding Next button");
                        const nextButton = document.createElement('button');
                        nextButton.className = 'button';
                        nextButton.textContent = 'Next →';
                        nextButton.onclick = function() {
                            loadLogs(serviceName, container, pagination.page + 1);
                        };
                        paginationContainer.appendChild(nextButton);
                    }
                } else {
                    console.log("Not adding pagination controls - not enough pages");
                }
                
                // Always add refresh button
                const refreshBtn = document.createElement('button');
                refreshBtn.className = 'button reload-btn';
                refreshBtn.textContent = 'Refresh Logs';
                
                if (pagination && pagination.total_pages > 1) {
                    refreshBtn.style.marginLeft = '15px';
                }
                
                refreshBtn.onclick = function() {
                    loadLogs(serviceName, container, pagination ? pagination.page : 1);
                };
                
                paginationContainer.appendChild(refreshBtn);
                container.appendChild(paginationContainer);
                
                // Add a debug indicator showing the number of children in the pagination container
                console.log(`Pagination container has ${paginationContainer.childNodes.length} child elements`);
                
            } else {
                container.innerHTML = '<div class="info-message">No logs available for this service.</div>';
            }
        })
        .catch(error => {
            console.error('Error fetching logs:', error);
            container.innerHTML = `<div class="error-message">Failed to load logs: ${error.message}</div>`;
        });
}

// Improved collapsible section function to handle special formatting for ExecStart
function addCollapsibleSection(parent, title, data) {
    if (!data || Object.keys(data).length === 0) return;
    
    const button = document.createElement('button');
    button.className = 'collapsible';
    button.textContent = title;
    parent.appendChild(button);
    
    const content = document.createElement('div');
    content.className = 'collapsible-content';
    content.style.padding = '0 18px';
    
    const table = document.createElement('table');
    table.className = 'metadata-table';
    
    // Sort keys for consistent display
    const sortedKeys = Object.keys(data).sort();
    
    for (const key of sortedKeys) {
        const value = data[key];
        const row = table.insertRow();
        const keyCell = row.insertCell(0);
        const valueCell = row.insertCell(1);
        
        keyCell.textContent = key;
        
        // Special handling for different value types
        if (key === 'ExecStart' && typeof value === 'string' && value.includes('\\')) {
            // Format multi-line ExecStart commands
            const pre = document.createElement('pre');
            pre.style.margin = '0';
            pre.style.whiteSpace = 'pre-wrap';
            pre.style.wordBreak = 'break-all';
            pre.textContent = value.replace(/\\/g, '\\\n  ');  // Add line breaks after each backslash
            valueCell.appendChild(pre);
        } else if (Array.isArray(value)) {
            // Handle array values like Environment variables
            const list = document.createElement('ul');
            list.style.margin = '0';
            list.style.paddingLeft = '20px';
            
            value.forEach(item => {
                const listItem = document.createElement('li');
                listItem.textContent = item;
                list.appendChild(listItem);
            });
            
            valueCell.appendChild(list);
        } else {
            // Regular values
            valueCell.textContent = value;
        }
    }
    
    content.appendChild(table);
    parent.appendChild(content);
    
    // Add click handler for collapsible section
    button.addEventListener("click", function() {
        this.classList.toggle("active");
        
        // Toggle max-height properly
        if (content.style.maxHeight) {
            content.style.maxHeight = null;
        } else {
            content.style.maxHeight = content.scrollHeight + "px";
        }
    });
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', loadServices);
