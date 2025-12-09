// Dashboard JavaScript

let debtPieChart = null;
let monthlyTrendsChart = null;

// Store debt data for tooltip lookups
let debtByPersonData = [];

// Format currency in Vietnamese
function formatCurrency(amount) {
    return new Intl.NumberFormat('vi-VN', {
        style: 'currency',
        currency: 'VND',
        maximumFractionDigits: 0
    }).format(amount);
}

// Format date in Vietnamese
function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString('vi-VN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit'
    });
}

// Fetch and display summary data
async function loadSummary() {
    try {
        const response = await fetch('/api/dashboard/summary');
        if (!response.ok) throw new Error('Failed to load summary');
        
        const data = await response.json();
        
        document.getElementById('total-balance').textContent = formatCurrency(data.total_net_balance || 0);
        document.getElementById('positive-balance').textContent = formatCurrency(data.total_positive || 0);
        document.getElementById('negative-balance').textContent = formatCurrency(Math.abs(data.total_negative || 0));
        document.getElementById('debtor-count').textContent = data.debtor_count || 0;
        
        // Update colors based on total balance
        const totalBalanceEl = document.getElementById('total-balance');
        if (data.total_net_balance > 0) {
            totalBalanceEl.classList.add('text-green-600');
            totalBalanceEl.classList.remove('text-red-600');
        } else if (data.total_net_balance < 0) {
            totalBalanceEl.classList.add('text-red-600');
            totalBalanceEl.classList.remove('text-green-600');
        }
    } catch (error) {
        console.error('Error loading summary:', error);
    }
}

// Fetch and render debt by person pie chart
async function loadDebtByPerson() {
    try {
        const response = await fetch('/api/dashboard/debt-by-person');
        if (!response.ok) throw new Error('Failed to load debt data');
        
        const data = await response.json();
        
        // API returns direct array with {debtor_id, name, balance}
        if (!data || data.length === 0) {
            document.getElementById('debt-pie-chart').style.display = 'none';
            document.getElementById('pie-chart-empty').classList.remove('hidden');
            return;
        }
        
        // Store for tooltip lookups
        debtByPersonData = data;
        
        const ctx = document.getElementById('debt-pie-chart').getContext('2d');
        
        // Generate colors
        const colors = data.map((_, i) => {
            const hue = (i * 137.5) % 360;
            return `hsl(${hue}, 70%, 60%)`;
        });
        
        if (debtPieChart) {
            debtPieChart.destroy();
        }
        
        debtPieChart = new Chart(ctx, {
            type: 'pie',
            data: {
                labels: data.map(item => item.name),
                datasets: [{
                    data: data.map(item => Math.abs(item.balance)),
                    backgroundColor: colors,
                    borderWidth: 2,
                    borderColor: '#fff'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'right',
                        labels: {
                            boxWidth: 12,
                            padding: 15
                        }
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                const item = debtByPersonData[context.dataIndex];
                                // balance > 0 means they owe you
                                const prefix = item.balance >= 0 ? 'Nợ bạn: ' : 'Bạn nợ: ';
                                return prefix + formatCurrency(Math.abs(item.balance));
                            }
                        }
                    }
                }
            }
        });
    } catch (error) {
        console.error('Error loading debt by person:', error);
    }
}

// Fetch and render monthly trends line chart
async function loadMonthlyTrends() {
    try {
        const response = await fetch('/api/dashboard/monthly-trends');
        if (!response.ok) throw new Error('Failed to load trends data');
        
        const data = await response.json();
        
        // API returns array of {month, net_change}
        if (!data || data.length === 0) {
            document.getElementById('monthly-trends-chart').style.display = 'none';
            document.getElementById('line-chart-empty').classList.remove('hidden');
            return;
        }
        
        const ctx = document.getElementById('monthly-trends-chart').getContext('2d');
        
        if (monthlyTrendsChart) {
            monthlyTrendsChart.destroy();
        }
        
        const months = data.map(item => item.month);
        const netChanges = data.map(item => parseFloat(item.net_change));
        
        monthlyTrendsChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: months,
                datasets: [
                    {
                        label: 'Thay đổi ròng',
                        data: netChanges,
                        borderColor: '#3b82f6',
                        backgroundColor: 'rgba(59, 130, 246, 0.1)',
                        fill: true,
                        tension: 0.4
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    intersect: false,
                    mode: 'index'
                },
                scales: {
                    y: {
                        ticks: {
                            callback: function(value) {
                                return formatCurrency(value);
                            }
                        }
                    }
                },
                plugins: {
                    legend: {
                        position: 'top'
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                return context.dataset.label + ': ' + formatCurrency(context.raw);
                            }
                        }
                    }
                }
            }
        });
    } catch (error) {
        console.error('Error loading monthly trends:', error);
    }
}

// Fetch and display transaction history
async function loadTransactionHistory() {
    try {
        const response = await fetch('/api/dashboard/history?limit=50');
        if (!response.ok) throw new Error('Failed to load history');
        
        const data = await response.json();
        const tableBody = document.getElementById('transaction-table');
        
        // API returns direct array with {id, debtor_id, debtor_name, amount, type, note, created_at}
        if (!data || data.length === 0) {
            tableBody.innerHTML = `
                <tr>
                    <td colspan="4" class="px-4 py-8 text-center text-gray-500">
                        Chưa có giao dịch nào
                    </td>
                </tr>
            `;
            document.getElementById('pagination').innerHTML = '';
            return;
        }
        
        tableBody.innerHTML = data.map(item => {
            // type is "DEBT" or "CREDIT"
            // DEBT = they owe you more (positive for you)
            // CREDIT = they paid back (negative for you)
            const isPositive = item.type === 'DEBT';
            const displayAmount = isPositive ? item.amount : -Math.abs(item.amount);
            
            return `
                <tr>
                    <td class="px-4 py-3 text-sm text-gray-600">${formatDate(item.created_at)}</td>
                    <td class="px-4 py-3 text-sm text-gray-800">${escapeHtml(item.debtor_name)}</td>
                    <td class="px-4 py-3 text-sm text-gray-600">${escapeHtml(item.note || '-')}</td>
                    <td class="px-4 py-3 text-sm text-right ${isPositive ? 'amount-positive' : 'amount-negative'}">
                        ${isPositive ? '+' : ''}${formatCurrency(displayAmount)}
                    </td>
                </tr>
            `;
        }).join('');
        
        // No pagination from API, hide pagination controls
        document.getElementById('pagination').innerHTML = '';
    } catch (error) {
        console.error('Error loading history:', error);
        document.getElementById('transaction-table').innerHTML = `
            <tr>
                <td colspan="4" class="px-4 py-8 text-center text-red-500">
                    Lỗi tải dữ liệu
                </td>
            </tr>
        `;
    }
}

// Escape HTML to prevent XSS
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Initialize dashboard on page load
document.addEventListener('DOMContentLoaded', function() {
    loadSummary();
    loadDebtByPerson();
    loadMonthlyTrends();
    loadTransactionHistory();
});
