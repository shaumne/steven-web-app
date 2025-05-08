// Settings page JavaScript

document.addEventListener('DOMContentLoaded', function() {
    // Save IG Settings
    document.getElementById('saveIgSettings').addEventListener('click', function() {
        const settings = {
            ig_username: document.getElementById('igUsername').value,
            ig_password: document.getElementById('igPassword').value,
            ig_api_key: document.getElementById('igApiKey').value,
            ig_demo: document.getElementById('igDemo').checked,
            max_open_positions: parseInt(document.getElementById('maxOpenPositions').value),
            max_total_positions_and_orders: parseInt(document.getElementById('maxTotalPositionsAndOrders').value),
            alert_max_age_seconds: parseInt(document.getElementById('alertMaxAge').value),
            max_deal_age_minutes: parseInt(document.getElementById('maxDealAge').value),
            default_order_type: document.getElementById('defaultOrderType').value,
            check_existing_position: document.getElementById('checkExistingPosition').checked,
            check_same_day_trades: document.getElementById('checkSameDayTrades').checked,
            check_open_position_limit: document.getElementById('checkOpenPositionLimit').checked,
            check_alert_timestamp: document.getElementById('checkAlertTimestamp').checked,
            check_dividend_date: document.getElementById('checkDividendDate').checked,
            check_max_deal_age: document.getElementById('checkMaxDealAge').checked,
            check_total_positions_and_orders: document.getElementById('checkTotalPositionsAndOrders').checked
        };

        // Save settings via API
        fetch('/api/save_settings', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(settings)
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                showAlert('success', 'Settings saved successfully');
            } else {
                showAlert('error', data.message || 'Failed to save settings');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            showAlert('error', 'Failed to save settings');
        });
    });

    // Test Connection
    document.getElementById('testConnection').addEventListener('click', function() {
        fetch('/api/test_connection')
        .then(response => response.json())
        .then(data => {
            const statusElement = document.getElementById('apiStatus');
            if (data.status === 'success') {
                statusElement.className = 'alert alert-success';
                statusElement.innerHTML = '<i class="bi bi-check-circle"></i> Connected';
                showAlert('success', 'Connection successful');
            } else {
                statusElement.className = 'alert alert-danger';
                statusElement.innerHTML = '<i class="bi bi-x-circle"></i> Disconnected';
                showAlert('error', data.message || 'Connection failed');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            showAlert('error', 'Connection test failed');
        });
    });

    // Edit buttons functionality
    const editButtons = {
        'editUsername': 'igUsername',
        'editPassword': 'igPassword',
        'editApiKey': 'igApiKey'
    };

    Object.entries(editButtons).forEach(([buttonId, inputId]) => {
        document.getElementById(buttonId).addEventListener('click', function() {
            const input = document.getElementById(inputId);
            input.readOnly = !input.readOnly;
            this.innerHTML = input.readOnly ? 
                '<i class="bi bi-pencil"></i>' : 
                '<i class="bi bi-check"></i>';
        });
    });

    // Copy webhook URL
    document.getElementById('copyWebhook').addEventListener('click', function() {
        const webhookUrl = document.getElementById('webhookUrl');
        navigator.clipboard.writeText(webhookUrl.value)
            .then(() => showAlert('success', 'Webhook URL copied to clipboard'))
            .catch(() => showAlert('error', 'Failed to copy webhook URL'));
    });

    // Test webhook
    document.getElementById('testWebhook').addEventListener('click', function() {
        fetch('/test/webhook', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                symbol: 'TEST:SYMBOL',
                direction: 'BUY',
                message: 'Test webhook'
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                showAlert('success', 'Webhook test successful');
            } else {
                showAlert('error', data.message || 'Webhook test failed');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            showAlert('error', 'Webhook test failed');
        });
    });
});

// Show alert message
function showAlert(type, message) {
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
    alertDiv.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    `;
    document.querySelector('.container-fluid').insertBefore(alertDiv, document.querySelector('.container-fluid').firstChild);
    
    // Auto dismiss after 5 seconds
    setTimeout(() => {
        alertDiv.remove();
    }, 5000);
} 