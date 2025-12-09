// Dashboard JavaScript

let debtPieChart = null;
let monthlyTrendsChart = null;
let currentPage = 1;

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
        
        document.getElementById('total-balance').textContent = formatCurrency(data.total_balance || 0);
        document.getElementById('positive-balance').textContent = formatCurrency(data.positive_balance || 0);
        document.getElementById('negative-balance').textContent = formatCurrency(Math.abs(data.negative_balance || 0));
        document.getElementById('debtor-count').textContent = data.debtor_count || 0;
        
        // Update colors based on total balance
        const totalBalanceEl = document.getElementById('total-balance');
        if (data.total_balance > 0) {
            totalBalanceEl.classList.add('text-green-600');
            totalBalanceEl.classList.remove('text-red-600');
        } else if (data.total_balance < 0) {
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
        
        if (!data.items || data.items.length === 0) {
            document.getElementById('debt-pie-chart').style.display = 'none';
            document.getElementById('pie-chart-empty').classList.remove('hidden');
            return;
        }
        
        const ctx = document.getElementById('debt-pie-chart').getContext('2d');
        
        // Generate colors
        const colors = data.items.map((_, i) => {
            const hue = (i * 137.5) % 360;
            return `hsl(${hue}, 70%, 60%)`;
        });
        
        if (debtPieChart) {
            debtPieChart.destroy();
        }
        
        debtPieChart = new Chart(ctx, {
            type: 'pie',
            data: {
                labels: data.items.map(item => item.name),
                datasets: [{
                    data: data.items.map(item => Math.abs(item.amount)),
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
                                const item = data.items[context.dataIndex];
                                const prefix = item.amount >= 0 ? 'Nợ bạn: ' : 'Bạn nợ: ';
                                return prefix + formatCurrency(Math.abs(item.amount));
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
        
        if (!data.months || data.months.length === 0) {
            document.getElementById('monthly-trends-chart').style.display = 'none';
            document.getElementById('line-chart-empty').classList.remove('hidden');
            return;
        }
        
        const ctx = document.getElementById('monthly-trends-chart').getContext('2d');
        
        if (monthlyTrendsChart) {
            monthlyTrendsChart.destroy();
        }
        
        monthlyTrendsChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: data.months,
                datasets: [
                    {
                        label: 'Thu',
                        data: data.income,
                        borderColor: '#16a34a',
                        backgroundColor: 'rgba(22, 163, 74, 0.1)',
                        fill: true,
                        tension: 0.4
                    },
                    {
                        label: 'Chi',
                        data: data.expense,
                        borderColor: '#dc2626',
                        backgroundColor: 'rgba(220, 38, 38, 0.1)',
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
                        beginAtZero: true,
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
async function loadTransactionHistory(page = 1) {
    try {
        const response = await fetch(`/api/dashboard/history?page=${page}&limit=10`);
        if (!response.ok) throw new Error('Failed to load history');
        
        const data = await response.json();
        const tableBody = document.getElementById('transaction-table');
        
        if (!data.items || data.items.length === 0) {
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
        
        tableBody.innerHTML = data.items.map(item => `
            <tr>
                <td class="px-4 py-3 text-sm text-gray-600">${formatDate(item.date)}</td>
                <td class="px-4 py-3 text-sm text-gray-800">${escapeHtml(item.person_name)}</td>
                <td class="px-4 py-3 text-sm text-gray-600">${escapeHtml(item.description || '-')}</td>
                <td class="px-4 py-3 text-sm text-right ${item.amount >= 0 ? 'amount-positive' : 'amount-negative'}">
                    ${item.amount >= 0 ? '+' : ''}${formatCurrency(item.amount)}
                </td>
            </tr>
        `).join('');
        
        // Render pagination
        renderPagination(data.page, data.total_pages);
        currentPage = page;
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

// Render pagination controls
function renderPagination(currentPage, totalPages) {
    const paginationEl = document.getElementById('pagination');
    
    if (totalPages <= 1) {
        paginationEl.innerHTML = '';
        return;
    }
    
    let html = '';
    
    // Previous button
    html += `
        <button class="pagination-btn" onclick="loadTransactionHistory(${currentPage - 1})" 
                ${currentPage === 1 ? 'disabled' : ''}>
            ← Trước
        </button>
    `;
    
    // Page numbers
    const startPage = Math.max(1, currentPage - 2);
    const endPage = Math.min(totalPages, currentPage + 2);
    
    for (let i = startPage; i <= endPage; i++) {
        html += `
            <button class="pagination-btn ${i === currentPage ? 'active' : ''}" 
                    onclick="loadTransactionHistory(${i})">
                ${i}
            </button>
        `;
    }
    
    // Next button
    html += `
        <button class="pagination-btn" onclick="loadTransactionHistory(${currentPage + 1})"
                ${currentPage === totalPages ? 'disabled' : ''}>
            Sau →
        </button>
    `;
    
    paginationEl.innerHTML = html;
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
