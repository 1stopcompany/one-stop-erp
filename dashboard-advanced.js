/**
 * ADVANCED DASHBOARD JAVASCRIPT
 * Construction Reports Management System
 * ============================================================================
 */

// ============================================================================
// CONFIGURATION & STATE
// ============================================================================

const DashboardConfig = {
    apiBase: '/api',
    refreshInterval: 30000, // 30 seconds
    animationDuration: 300,
    chartUpdateDuration: 500,
    toastDuration: 3000,
    maxNotifications: 5
};

const DashboardState = {
    currentTab: 'overview',
    charts: {},
    data: {
        dailyReports: [],
        monthlyReports: [],
        metrics: {},
        activity: []
    },
    isLoading: false,
    filters: {
        dateRange: 'month',
        status: 'all',
        project: 'all'
    }
};

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

/**
 * Debounce function to limit function calls
 */
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

/**
 * Throttle function to limit function calls
 */
function throttle(func, limit) {
    let inThrottle;
    return function(...args) {
        if (!inThrottle) {
            func.apply(this, args);
            inThrottle = true;
            setTimeout(() => inThrottle = false, limit);
        }
    };
}

/**
 * Format number with commas
 */
function formatNumber(num) {
    return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

/**
 * Format date to readable format
 */
function formatDate(date) {
    const options = { year: 'numeric', month: 'short', day: 'numeric' };
    return new Date(date).toLocaleDateString('en-US', options);
}

/**
 * Format time to readable format
 */
function formatTime(date) {
    const options = { hour: '2-digit', minute: '2-digit' };
    return new Date(date).toLocaleTimeString('en-US', options);
}

/**
 * Get time ago string
 */
function getTimeAgo(date) {
    const seconds = Math.floor((new Date() - new Date(date)) / 1000);
    
    if (seconds < 60) return 'just now';
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
    if (seconds < 604800) return `${Math.floor(seconds / 86400)}d ago`;
    
    return formatDate(date);
}

/**
 * Generate unique ID
 */
function generateId() {
    return '_' + Math.random().toString(36).substr(2, 9);
}

/**
 * Clone object
 */
function cloneObject(obj) {
    return JSON.parse(JSON.stringify(obj));
}

// ============================================================================
// NOTIFICATION SYSTEM
// ============================================================================

class NotificationManager {
    constructor() {
        this.notifications = [];
        this.container = null;
        this.init();
    }

    init() {
        this.container = document.createElement('div');
        this.container.id = 'notification-container';
        this.container.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 9999;
            max-width: 400px;
        `;
        document.body.appendChild(this.container);
    }

    show(message, type = 'info', duration = DashboardConfig.toastDuration) {
        const id = generateId();
        const notification = document.createElement('div');
        notification.id = id;
        notification.className = `notification notification-${type} animate-slide-up`;
        notification.innerHTML = `
            <i class="fas fa-${this.getIcon(type)}"></i>
            <span>${message}</span>
            <button onclick="notificationManager.close('${id}')" style="background: none; border: none; color: inherit; cursor: pointer; font-size: 16px;">
                <i class="fas fa-times"></i>
            </button>
        `;

        this.container.appendChild(notification);
        this.notifications.push(id);

        if (this.notifications.length > DashboardConfig.maxNotifications) {
            const oldId = this.notifications.shift();
            const oldNotification = document.getElementById(oldId);
            if (oldNotification) oldNotification.remove();
        }

        if (duration > 0) {
            setTimeout(() => this.close(id), duration);
        }

        return id;
    }

    close(id) {
        const notification = document.getElementById(id);
        if (notification) {
            notification.style.animation = 'slideInUp 0.3s ease-out reverse';
            setTimeout(() => notification.remove(), 300);
            this.notifications = this.notifications.filter(n => n !== id);
        }
    }

    getIcon(type) {
        const icons = {
            success: 'check-circle',
            warning: 'exclamation-circle',
            danger: 'times-circle',
            info: 'info-circle'
        };
        return icons[type] || 'info-circle';
    }

    success(message, duration) {
        return this.show(message, 'success', duration);
    }

    warning(message, duration) {
        return this.show(message, 'warning', duration);
    }

    danger(message, duration) {
        return this.show(message, 'danger', duration);
    }

    info(message, duration) {
        return this.show(message, 'info', duration);
    }
}

// Initialize notification manager
const notificationManager = new NotificationManager();

// ============================================================================
// DATA MANAGEMENT
// ============================================================================

class DataManager {
    static async fetchData(endpoint) {
        try {
            DashboardState.isLoading = true;
            const response = await fetch(`${DashboardConfig.apiBase}${endpoint}`);
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const data = await response.json();
            DashboardState.isLoading = false;
            return data;
        } catch (error) {
            console.error('Fetch error:', error);
            DashboardState.isLoading = false;
            notificationManager.danger('Failed to fetch data');
            return null;
        }
    }

    static async postData(endpoint, data) {
        try {
            DashboardState.isLoading = true;
            const response = await fetch(`${DashboardConfig.apiBase}${endpoint}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                body: JSON.stringify(data)
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const result = await response.json();
            DashboardState.isLoading = false;
            return result;
        } catch (error) {
            console.error('Post error:', error);
            DashboardState.isLoading = false;
            notificationManager.danger('Failed to save data');
            return null;
        }
    }

    static getCSRFToken() {
        const name = 'csrftoken';
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    static generateMockData() {
        return {
            dailyReports: [
                { id: 1, number: 'DCR-001', date: new Date(), status: 'approved', engineer: 'Ahmed' },
                { id: 2, number: 'DCR-002', date: new Date(), status: 'submitted', engineer: 'Ahmed' },
                { id: 3, number: 'DCR-003', date: new Date(), status: 'draft', engineer: 'Ahmed' }
            ],
            monthlyReports: [
                { id: 1, number: 'MR-001', period: 'Dec 2025', status: 'approved', engineer: 'Ahmed' },
                { id: 2, number: 'MR-002', period: 'Nov 2025', status: 'submitted', engineer: 'Ahmed' },
                { id: 3, number: 'MR-003', period: 'Oct 2025', status: 'pending', engineer: 'Ahmed' }
            ],
            metrics: {
                dailySubmittedToday: 12,
                monthlyPending: 5,
                totalApproved: 48,
                drafts: 8
            }
        };
    }
}

// ============================================================================
// CHART MANAGEMENT
// ============================================================================

class ChartManager {
    static initDailyChart(containerId) {
        const ctx = document.getElementById(containerId);
        if (!ctx) return;

        if (DashboardState.charts.daily) {
            DashboardState.charts.daily.destroy();
        }

        DashboardState.charts.daily = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
                datasets: [
                    {
                        label: 'Submitted',
                        data: [6, 8, 7, 9, 8, 10, 4],
                        backgroundColor: '#3b82f6',
                        borderRadius: 6,
                        borderSkipped: false,
                        animation: {
                            duration: DashboardConfig.chartUpdateDuration
                        }
                    },
                    {
                        label: 'Approved',
                        data: [5, 7, 6, 8, 7, 9, 3],
                        backgroundColor: '#10b981',
                        borderRadius: 6,
                        borderSkipped: false,
                        animation: {
                            duration: DashboardConfig.chartUpdateDuration
                        }
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: true,
                        position: 'top',
                        labels: {
                            usePointStyle: true,
                            padding: 15,
                            font: { size: 12, weight: '600' }
                        }
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        max: 12,
                        ticks: {
                            stepSize: 3,
                            font: { size: 12 }
                        },
                        grid: {
                            color: 'rgba(0, 0, 0, 0.05)'
                        }
                    },
                    x: {
                        ticks: {
                            font: { size: 12 }
                        },
                        grid: {
                            display: false
                        }
                    }
                }
            }
        });
    }

    static initMonthlyChart(containerId) {
        const ctx = document.getElementById(containerId);
        if (!ctx) return;

        if (DashboardState.charts.monthly) {
            DashboardState.charts.monthly.destroy();
        }

        DashboardState.charts.monthly = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: ['Approved', 'Pending', 'Draft'],
                datasets: [{
                    data: [7, 5, 0],
                    backgroundColor: [
                        '#10b981',
                        '#f59e0b',
                        '#e5e7eb'
                    ],
                    borderColor: '#ffffff',
                    borderWidth: 3,
                    animation: {
                        duration: DashboardConfig.chartUpdateDuration
                    }
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: true,
                        position: 'bottom',
                        labels: {
                            usePointStyle: true,
                            padding: 15,
                            font: { size: 12, weight: '600' }
                        }
                    }
                }
            }
        });
    }

    static updateChart(chartName, newData) {
        const chart = DashboardState.charts[chartName];
        if (!chart) return;

        chart.data.datasets.forEach((dataset, index) => {
            if (newData.datasets[index]) {
                dataset.data = newData.datasets[index].data;
            }
        });

        chart.update(DashboardConfig.chartUpdateDuration);
    }
}

// ============================================================================
// TAB MANAGEMENT
// ============================================================================

class TabManager {
    static switchTab(tabName) {
        // Hide all tabs
        document.querySelectorAll('.tab-content').forEach(tab => {
            tab.classList.remove('active');
        });

        // Remove active class from all buttons
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.classList.remove('active');
        });

        // Show selected tab
        const selectedTab = document.getElementById(tabName);
        if (selectedTab) {
            selectedTab.classList.add('active');
        }

        // Add active class to clicked button
        const activeBtn = document.querySelector(`[onclick*="'${tabName}'"]`);
        if (activeBtn) {
            activeBtn.classList.add('active');
        }

        DashboardState.currentTab = tabName;

        // Initialize charts for overview tab
        if (tabName === 'overview') {
            setTimeout(() => {
                ChartManager.initDailyChart('dailyChart');
                ChartManager.initMonthlyChart('monthlyChart');
            }, 100);
        }

        notificationManager.info(`Switched to ${tabName} view`);
    }
}

// ============================================================================
// REPORT MANAGEMENT
// ============================================================================

class ReportManager {
    static async createReport(type) {
        notificationManager.info(`Creating new ${type} report...`);
        
        // In a real application, this would navigate to the report creation page
        // window.location.href = `/reports/${type}/create/`;
        
        setTimeout(() => {
            notificationManager.success(`${type} report created successfully!`);
        }, 1000);
    }

    static async submitReport(reportId) {
        const result = await DataManager.postData(`/reports/${reportId}/submit/`, {});
        if (result) {
            notificationManager.success('Report submitted for approval');
            this.refreshReports();
        }
    }

    static async approveReport(reportId) {
        const result = await DataManager.postData(`/reports/${reportId}/approve/`, {});
        if (result) {
            notificationManager.success('Report approved successfully');
            this.refreshReports();
        }
    }

    static async exportReport(reportId, format = 'pdf') {
        window.location.href = `/reports/${reportId}/export-${format}/`;
        notificationManager.info(`Exporting report as ${format.toUpperCase()}...`);
    }

    static async refreshReports() {
        const data = DataManager.generateMockData();
        DashboardState.data = data;
        this.updateReportLists();
        this.updateMetrics();
    }

    static updateReportLists() {
        // Update daily reports list
        const dailyList = document.querySelector('[data-list="daily"]');
        if (dailyList) {
            dailyList.innerHTML = DashboardState.data.dailyReports.map(report => `
                <div class="report-item">
                    <div class="report-info">
                        <div class="report-title">${report.number}</div>
                        <div class="report-meta">
                            <span><i class="fas fa-calendar"></i> ${formatDate(report.date)}</span>
                            <span><i class="fas fa-user"></i> ${report.engineer}</span>
                        </div>
                    </div>
                    <span class="report-status status-${report.status}">
                        ${this.getStatusIcon(report.status)} ${this.formatStatus(report.status)}
                    </span>
                </div>
            `).join('');
        }

        // Update monthly reports list
        const monthlyList = document.querySelector('[data-list="monthly"]');
        if (monthlyList) {
            monthlyList.innerHTML = DashboardState.data.monthlyReports.map(report => `
                <div class="report-item">
                    <div class="report-info">
                        <div class="report-title">${report.number}</div>
                        <div class="report-meta">
                            <span><i class="fas fa-calendar-range"></i> ${report.period}</span>
                            <span><i class="fas fa-user"></i> ${report.engineer}</span>
                        </div>
                    </div>
                    <span class="report-status status-${report.status}">
                        ${this.getStatusIcon(report.status)} ${this.formatStatus(report.status)}
                    </span>
                </div>
            `).join('');
        }
    }

    static updateMetrics() {
        const metrics = DashboardState.data.metrics;
        
        // Update metric values
        const metricsElements = document.querySelectorAll('.metric-value');
        if (metricsElements[0]) metricsElements[0].textContent = metrics.dailySubmittedToday;
        if (metricsElements[1]) metricsElements[1].textContent = metrics.monthlyPending;
        if (metricsElements[2]) metricsElements[2].textContent = metrics.totalApproved;
        if (metricsElements[3]) metricsElements[3].textContent = metrics.drafts;
    }

    static getStatusIcon(status) {
        const icons = {
            approved: '✓',
            submitted: '⏳',
            draft: '✎',
            pending: '⚠'
        };
        return icons[status] || '•';
    }

    static formatStatus(status) {
        return status.charAt(0).toUpperCase() + status.slice(1);
    }
}

// ============================================================================
// DASHBOARD INITIALIZATION
// ============================================================================

class Dashboard {
    static init() {
        console.log('Initializing Dashboard...');
        
        // Initialize charts
        ChartManager.initDailyChart('dailyChart');
        ChartManager.initMonthlyChart('monthlyChart');

        // Load initial data
        ReportManager.refreshReports();

        // Setup event listeners
        this.setupEventListeners();

        // Setup auto-refresh
        this.setupAutoRefresh();

        console.log('Dashboard initialized successfully');
        notificationManager.success('Dashboard loaded successfully');
    }

    static setupEventListeners() {
        // Tab buttons
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const tabName = e.currentTarget.getAttribute('onclick').match(/'([^']+)'/)[1];
                TabManager.switchTab(tabName);
            });
        });

        // Report item clicks
        document.addEventListener('click', (e) => {
            if (e.target.closest('.report-item')) {
                const reportTitle = e.target.closest('.report-item').querySelector('.report-title').textContent;
                console.log('Clicked report:', reportTitle);
            }
        });

        // Window resize for responsive behavior
        window.addEventListener('resize', debounce(() => {
            Object.values(DashboardState.charts).forEach(chart => {
                if (chart) chart.resize();
            });
        }, 250));
    }

    static setupAutoRefresh() {
        setInterval(() => {
            if (!DashboardState.isLoading) {
                ReportManager.refreshReports();
                console.log('Dashboard auto-refreshed');
            }
        }, DashboardConfig.refreshInterval);
    }

    static refreshDashboard() {
        const button = event.target.closest('.btn');
        const originalHTML = button.innerHTML;
        button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Refreshing...';
        button.disabled = true;

        setTimeout(() => {
            button.innerHTML = originalHTML;
            button.disabled = false;
            ReportManager.refreshReports();
            notificationManager.success('Dashboard refreshed');
        }, 1500);
    }
}

// ============================================================================
// INITIALIZATION ON PAGE LOAD
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
    Dashboard.init();
});

// Export functions for inline onclick handlers
window.switchTab = (tabName) => TabManager.switchTab(tabName);
window.createNewReport = (type) => ReportManager.createReport(type);
window.refreshDashboard = () => Dashboard.refreshDashboard();
window.submitReport = (reportId) => ReportManager.submitReport(reportId);
window.approveReport = (reportId) => ReportManager.approveReport(reportId);
window.exportReport = (reportId, format) => ReportManager.exportReport(reportId, format);
