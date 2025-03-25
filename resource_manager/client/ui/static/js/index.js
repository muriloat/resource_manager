// Function to handle adding a new host row
function addNewHostRow() {
    // Remove any existing new host row
    const existingNewRow = document.querySelector('.new-host-row');
    if (existingNewRow) {
        existingNewRow.remove();
    }
    
    const table = document.getElementById('host-table');
    const tbody = table.querySelector('tbody');
    
    // Create new row
    const newRow = document.createElement('tr');
    newRow.className = 'new-host-row';
    
    // Create hostname cell (formerly host-id)
    const hostnameTd = document.createElement('td');
    const hostnameInput = document.createElement('input');
    hostnameInput.type = 'text';
    hostnameInput.id = 'host-id'; // Keep ID for compatibility
    hostnameInput.placeholder = '<server-01>';
    hostnameTd.appendChild(hostnameInput);
    newRow.appendChild(hostnameTd);
    
    // Create description cell (formerly name)
    const descriptionTd = document.createElement('td');
    const descriptionInput = document.createElement('input');
    descriptionInput.type = 'text';
    descriptionInput.id = 'host-name'; // Keep ID for compatibility
    descriptionInput.placeholder = '<Production Server>';
    descriptionTd.appendChild(descriptionInput);
    newRow.appendChild(descriptionTd);
    
    // Create URL cell
    const urlTd = document.createElement('td');
    const urlInput = document.createElement('input');
    urlInput.type = 'text';
    urlInput.id = 'host-url';
    urlInput.placeholder = '<http://192.168.1.100:5000>';
    urlTd.appendChild(urlInput);
    newRow.appendChild(urlTd);
    
    // Create status cell (empty)
    const statusTd = document.createElement('td');
    statusTd.textContent = '-';
    newRow.appendChild(statusTd);
    
    // Create actions cell with Add button
    const actionsTd = document.createElement('td');
    
    // Add Host button
    const addButton = document.createElement('button');
    addButton.className = 'button';
    addButton.textContent = 'Add Host';
    addButton.onclick = addHost;
    actionsTd.appendChild(addButton);
    
    // Cancel button
    const cancelButton = document.createElement('button');
    cancelButton.className = 'button delete';
    cancelButton.textContent = 'Cancel';
    cancelButton.onclick = function() {
        newRow.remove();
    };
    actionsTd.appendChild(cancelButton);
    
    // Hidden timeout input
    const timeoutInput = document.createElement('input');
    timeoutInput.type = 'hidden';
    timeoutInput.id = 'host-timeout';
    timeoutInput.value = '80';
    actionsTd.appendChild(timeoutInput);
    
    newRow.appendChild(actionsTd);
    
    // Insert at the beginning of the table
    if (tbody.firstChild) {
        tbody.insertBefore(newRow, tbody.firstChild);
    } else {
        tbody.appendChild(newRow);
    }
    
    // Focus on the first input
    hostnameInput.focus();
}

// Add click handler to the + button
document.getElementById('add-host-button').addEventListener('click', addNewHostRow);

function viewHost(hostId) {
    window.location.href = '/host/' + hostId;
}

function editHost(hostId) {
    // Get current host data from the table row
    const row = document.querySelector(`tr[data-host-id="${hostId}"]`);
    if (!row) return;
    
    // Remove any existing new host row
    const existingNewRow = document.querySelector('.new-host-row');
    if (existingNewRow && existingNewRow !== row) {
        existingNewRow.remove();
    }
    
    // Convert the regular row to an editable row
    row.classList.add('new-host-row');
    
    const hostname = row.cells[0].textContent;
    const description = row.cells[1].textContent;
    const url = row.cells[2].textContent;
    
    // Replace content with input fields
    const hostnameInput = document.createElement('input');
    hostnameInput.type = 'text';
    hostnameInput.id = 'host-id';
    hostnameInput.value = hostname;
    hostnameInput.disabled = true; // Can't change hostname during edit
    row.cells[0].textContent = '';
    row.cells[0].appendChild(hostnameInput);
    
    const descriptionInput = document.createElement('input');
    descriptionInput.type = 'text';
    descriptionInput.id = 'host-name';
    descriptionInput.value = description;
    row.cells[1].textContent = '';
    row.cells[1].appendChild(descriptionInput);
    
    const urlInput = document.createElement('input');
    urlInput.type = 'text';
    urlInput.id = 'host-url';
    urlInput.value = url;
    row.cells[2].textContent = '';
    row.cells[2].appendChild(urlInput);
    
    // Replace action buttons
    const actionsCell = row.cells[4];
    actionsCell.innerHTML = '';
    
    // Update button
    const updateButton = document.createElement('button');
    updateButton.className = 'button';
    updateButton.textContent = 'Update';
    updateButton.onclick = function() {
        updateHost(hostId);
    };
    actionsCell.appendChild(updateButton);
    
    // Cancel button
    const cancelButton = document.createElement('button');
    cancelButton.className = 'button delete';
    cancelButton.textContent = 'Cancel';
    cancelButton.onclick = function() {
        window.location.reload(); // Simple refresh to cancel
    };
    actionsCell.appendChild(cancelButton);
    
    // Hidden timeout input
    const timeoutInput = document.createElement('input');
    timeoutInput.type = 'hidden';
    timeoutInput.id = 'host-timeout';
    timeoutInput.value = '80';
    actionsCell.appendChild(timeoutInput);
}

function updateHost(hostId) {
    const hostname = document.getElementById('host-id').value;
    const description = document.getElementById('host-name').value;
    const hostUrl = document.getElementById('host-url').value;
    const hostTimeout = document.getElementById('host-timeout').value;
    
    if (!hostname || !description || !hostUrl) {
        alert('Please fill in all required fields.');
        return;
    }
    
    fetch('/api/hosts/' + hostId, {
        method: 'PUT',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            name: description,  // Changed from 'name' to match our UI terminology
            url: hostUrl,
            timeout: hostTimeout
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            window.location.reload();
        } else {
            alert('Failed to update host.');
        }
    });
}

function addHost() {
    const hostname = document.getElementById('host-id').value;
    const description = document.getElementById('host-name').value;
    const hostUrl = document.getElementById('host-url').value;
    const hostTimeout = document.getElementById('host-timeout').value;
    
    if (!hostname || !description || !hostUrl) {
        alert('Please fill in all required fields.');
        return;
    }
    
    fetch('/api/hosts', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            id: hostname,  // This is now the 'hostname' in UI terms
            name: description,  // This is now the 'description' in UI terms
            url: hostUrl,
            timeout: hostTimeout
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            window.location.reload();
        } else {
            alert('Failed to add host.');
        }
    });
}

function deleteHost(hostId) {
    if (confirm('Are you sure you want to delete this host?')) {
        fetch('/api/hosts/' + hostId, {
            method: 'DELETE'
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                window.location.reload();
            } else {
                alert('Failed to delete host.');
            }
        });
    }
}