/**
 * JSON Operations API client.
 *
 * Provides methods for working with JSON data files
 * that are shared with the Telegram bot.
 */

import apiClient from './client';

/**
 * JSON Operations API methods
 */
export const jsonAPI = {
  // ========== Unfound Equipment ==========

  /**
   * Add a new unfound equipment record
   * @param {Object} data - Equipment data
   * @param {string} data.serial_number - Serial number
   * @param {string} data.model_name - Model name
   * @param {string} data.employee_name - Employee name
   * @param {string} [data.brand_name] - Brand name
   * @param {string} [data.location] - Location code
   * @param {string} [data.equipment_type] - Equipment type
   * @param {string} [data.description] - Description
   * @param {string} [data.inventory_number] - Inventory number
   * @param {string} [data.ip_address] - IP address
   * @param {string} [data.status] - Status
   * @param {string} [data.branch] - Branch name
   * @param {string} [data.company] - Company name
   * @param {string} [data.db_name] - Database name
   * @param {Object} [data.additional_data] - Additional metadata
   * @returns {Promise<Object>} Created record
   */
  addUnfoundEquipment: (data) =>
    apiClient.post('/json/unfound', data),

  /**
   * Get unfound equipment records
   * @param {Object} [params] - Query parameters
   * @param {string} [params.db_name] - Filter by database name
   * @param {string} [params.branch] - Filter by branch
   * @param {string} [params.employee] - Filter by employee name
   * @param {number} [params.limit] - Maximum records to return
   * @returns {Promise<Array>} List of unfound equipment records
   */
  getUnfoundEquipment: (params) =>
    apiClient.get('/json/unfound', { params }),

  /**
   * Get unfound equipment statistics
   * @returns {Promise<Object>} Statistics data
   */
  getUnfoundStatistics: () =>
    apiClient.get('/json/unfound/statistics'),

  // ========== Transfers ==========

  /**
   * Add a new equipment transfer record
   * @param {Object} data - Transfer data
   * @param {string} data.serial_number - Serial number
   * @param {string} data.new_employee - New employee name
   * @param {string} [data.old_employee] - Old employee name
   * @param {string} [data.inv_no] - Inventory number
   * @param {string} [data.branch] - Branch name
   * @param {string} [data.location] - Location code
   * @param {string} [data.db_name] - Database name
   * @param {string} [data.act_pdf_path] - Path to PDF act
   * @param {Object} [data.additional_data] - Additional metadata
   * @returns {Promise<Object>} Created record
   */
  addTransfer: (data) =>
    apiClient.post('/json/transfers', data),

  /**
   * Get equipment transfer records
   * @param {Object} [params] - Query parameters
   * @param {string} [params.db_name] - Filter by database name
   * @param {string} [params.branch] - Filter by branch
   * @param {string} [params.employee] - Filter by employee name
   * @param {string} [params.serial_number] - Filter by serial number
   * @param {string} [params.from_date] - Filter from date (ISO format)
   * @param {string} [params.to_date] - Filter to date (ISO format)
   * @param {number} [params.limit] - Maximum records to return
   * @returns {Promise<Array>} List of transfer records
   */
  getTransfers: (params) =>
    apiClient.get('/json/transfers', { params }),

  /**
   * Bulk transfer multiple items
   * @param {Object} data - Bulk transfer data
   * @param {Array} data.items - List of items to transfer
   * @param {string} data.new_employee - Target employee name
   * @param {string} [data.branch] - Branch name
   * @param {string} [data.location] - Location code
   * @param {string} [data.db_name] - Database name
   * @returns {Promise<Object>} Operation result with success/failed counts
   */
  bulkTransfer: (data) =>
    apiClient.post('/json/transfers/bulk', data),

  /**
   * Get transfer statistics
   * @returns {Promise<Object>} Statistics data
   */
  getTransferStatistics: () =>
    apiClient.get('/json/transfers/statistics'),

  // ========== Cartridge Replacements ==========

  /**
   * Add a cartridge replacement record
   * @param {Object} data - Cartridge replacement data
   * @param {string} data.printer_model - Printer model
   * @param {string} data.cartridge_color - Cartridge color
   * @param {string} data.branch - Branch name
   * @param {string} data.location - Location code
   * @param {string} [data.serial_number] - Serial number
   * @param {string} [data.inv_no] - Inventory number
   * @param {string} [data.db_name] - Database name
   * @param {Object} [data.additional_data] - Additional metadata
   * @returns {Promise<Object>} Created record
   */
  addCartridgeReplacement: (data) =>
    apiClient.post('/json/works/cartridge', data),

  /**
   * Get cartridge replacement records
   * @param {Object} [params] - Query parameters
   * @param {string} [params.db_name] - Filter by database name
   * @param {string} [params.branch] - Filter by branch
   * @param {string} [params.location] - Filter by location
   * @param {string} [params.from_date] - Filter from date (ISO format)
   * @param {string} [params.to_date] - Filter to date (ISO format)
   * @param {number} [params.limit] - Maximum records to return
   * @returns {Promise<Array>} List of cartridge replacement records
   */
  getCartridgeReplacements: (params) =>
    apiClient.get('/json/works/cartridge', { params }),

  // ========== Battery Replacements ==========

  /**
   * Add a battery replacement record
   * @param {Object} data - Battery replacement data
   * @param {string} data.serial_number - Serial number
   * @param {string} data.branch - Branch name
   * @param {string} data.location - Location code
   * @param {string} [data.inv_no] - Inventory number
   * @param {string} [data.db_name] - Database name
   * @param {Object} [data.additional_data] - Additional metadata
   * @returns {Promise<Object>} Created record
   */
  addBatteryReplacement: (data) =>
    apiClient.post('/json/works/battery', data),

  /**
   * Get battery replacement records
   * @param {Object} [params] - Query parameters
   * @param {string} [params.db_name] - Filter by database name
   * @param {string} [params.branch] - Filter by branch
   * @param {string} [params.serial_number] - Filter by serial number
   * @param {string} [params.from_date] - Filter from date (ISO format)
   * @param {string} [params.to_date] - Filter to date (ISO format)
   * @param {number} [params.limit] - Maximum records to return
   * @returns {Promise<Array>} List of battery replacement records
   */
  getBatteryReplacements: (params) =>
    apiClient.get('/json/works/battery', { params }),

  // ========== Component Replacements ==========

  /**
   * Add a component replacement record
   * @param {Object} data - Component replacement data
   * @param {string} data.serial_number - Serial number
   * @param {string} data.component_type - Component type (fuser, drum, etc.)
   * @param {string} data.component_model - Component model
   * @param {string} data.branch - Branch name
   * @param {string} data.location - Location code
   * @param {string} [data.inv_no] - Inventory number
   * @param {string} [data.db_name] - Database name
   * @param {Object} [data.additional_data] - Additional metadata
   * @returns {Promise<Object>} Created record
   */
  addComponentReplacement: (data) =>
    apiClient.post('/json/works/component', data),

  /**
   * Get component replacement records
   * @param {Object} [params] - Query parameters
   * @param {string} [params.db_name] - Filter by database name
   * @param {string} [params.branch] - Filter by branch
   * @param {string} [params.component_type] - Filter by component type
   * @param {string} [params.serial_number] - Filter by serial number
   * @param {string} [params.from_date] - Filter from date (ISO format)
   * @param {string} [params.to_date] - Filter to date (ISO format)
   * @param {number} [params.limit] - Maximum records to return
   * @returns {Promise<Array>} List of component replacement records
   */
  getComponentReplacements: (params) =>
    apiClient.get('/json/works/component', { params }),

  // ========== PC Cleanings ==========

  /**
   * Add a PC cleaning record
   * @param {Object} data - PC cleaning data
   * @param {string} data.serial_number - Serial number
   * @param {string} data.employee - Employee name
   * @param {string} data.branch - Branch name
   * @param {string} data.location - Location code
   * @param {string} [data.inv_no] - Inventory number
   * @param {string} [data.db_name] - Database name
   * @param {Object} [data.additional_data] - Additional metadata
   * @returns {Promise<Object>} Created record
   */
  addPcCleaning: (data) =>
    apiClient.post('/json/works/cleaning', data),

  /**
   * Get PC cleaning records
   * @param {Object} [params] - Query parameters
   * @param {string} [params.db_name] - Filter by database name
   * @param {string} [params.branch] - Filter by branch
   * @param {string} [params.employee] - Filter by employee name
   * @param {string} [params.serial_number] - Filter by serial number
   * @param {string} [params.from_date] - Filter from date (ISO format)
   * @param {string} [params.to_date] - Filter to date (ISO format)
   * @param {number} [params.limit] - Maximum records to return
   * @returns {Promise<Array>} List of PC cleaning records
   */
  getPcCleanings: (params) =>
    apiClient.get('/json/works/cleaning', { params }),

  /**
   * Get PC cleaning statistics by branches
   * @param {Object} [params] - Query parameters
   * @param {number} [params.period_days] - Statistics window in days
   * @param {string} [params.db_name] - Optional database name override
   * @returns {Promise<Object>} Aggregated statistics
   */
  getPcCleaningStatistics: (params) =>
    apiClient.get('/json/works/cleaning/statistics', { params }),

  /**
   * Get MFU maintenance statistics by branches
   * @param {Object} [params] - Query parameters
   * @param {number} [params.period_days] - Statistics window in days
   * @param {string} [params.db_name] - Optional database name override
   * @returns {Promise<Object>} Aggregated statistics
   */
  getMfuStatistics: (params) =>
    apiClient.get('/json/works/mfu/statistics', { params }),

  /**
   * Get UPS battery replacement statistics
   * @param {Object} [params] - Query parameters
   * @param {number} [params.period_days] - Statistics window in days
   * @param {string} [params.db_name] - Optional database name override
   * @returns {Promise<Object>} Aggregated statistics
   */
  getBatteryStatistics: (params) =>
    apiClient.get('/json/works/battery/statistics', { params }),

  /**
   * Get PC components replacement statistics
   * @param {Object} [params] - Query parameters
   * @param {number} [params.period_days] - Statistics window in days
   * @param {string} [params.db_name] - Optional database name override
   * @returns {Promise<Object>} Aggregated statistics
   */
  getPcComponentsStatistics: (params) =>
    apiClient.get('/json/works/pc-components/statistics', { params }),

  /**
   * Export selected statistics tab to Excel
   * @param {string} tab - One of pc|mfu|battery|pc_components
   * @param {number} periodDays - Statistics window in days
   * @returns {Promise<Object>} Axios response with blob data
   */
  exportStatisticsExcel: (tab, periodDays) =>
    apiClient.get('/json/works/statistics/export', {
      params: { tab, period_days: periodDays },
      responseType: 'blob',
    }),

  /**
   * Get PC cleaning history for a specific serial number
   * @param {string} serial_number - Serial number
   * @param {string} [hw_serial_number] - Hardware serial number
   * @returns {Promise<Object>} History data with last_date, count, time_ago
   */
  getPcCleaningHistory: (serial_number, hw_serial_number) =>
    apiClient.get('/json/works/cleaning/history', {
      params: { serial_number, hw_serial_number }
    }),

  /**
   * Get cartridge replacement history for a specific equipment item
   * @param {string} [serial_number] - Serial number
   * @param {string} [hw_serial_number] - Hardware serial number
   * @param {string} [inv_no] - Inventory number
   * @param {string} [cartridge_color] - Cartridge color
   * @returns {Promise<Object>} History data with last_date, count, time_ago
   */
  getCartridgeReplacementHistory: (serial_number, hw_serial_number, inv_no, cartridge_color, cartridge_model) =>
    apiClient.get('/json/works/cartridge/history', {
      params: { serial_number, hw_serial_number, inv_no, cartridge_color, cartridge_model }
    }),

  /**
   * Get battery replacement history for a specific serial number
   * @param {string} serial_number - Serial number
   * @param {string} [hw_serial_number] - Hardware serial number
   * @returns {Promise<Object>} History data with last_date, count, time_ago
   */
  getBatteryReplacementHistory: (serial_number, hw_serial_number) =>
    apiClient.get('/json/works/battery/history', {
      params: { serial_number, hw_serial_number }
    }),

  /**
   * Get component replacement history for a specific serial number
   * @param {string} serial_number - Serial number
   * @param {string} [hw_serial_number] - Hardware serial number
   * @param {string} [component_type] - Component type key
   * @param {string} [component_name] - Human-readable component name
   * @returns {Promise<Object>} History data with last_date, count, time_ago
   */
  getComponentReplacementHistory: (serial_number, hw_serial_number, component_type, component_name) =>
    apiClient.get('/json/works/component/history', {
      params: { serial_number, hw_serial_number, component_type, component_name }
    }),

  // ========== All Works ==========

  /**
   * Get all works with optional filtering
   * @param {Object} [params] - Query parameters
   * @param {string} [params.work_type] - Filter by work type (cartridge, battery, component, cleaning)
   * @param {string} [params.db_name] - Filter by database name
   * @param {string} [params.from_date] - Filter from date (ISO format)
   * @param {string} [params.to_date] - Filter to date (ISO format)
   * @param {number} [params.limit] - Maximum records to return
   * @returns {Promise<Object>} Works data by type
   */
  getAllWorks: (params) =>
    apiClient.get('/json/works', { params }),

  /**
   * Bulk work operation for multiple items
   * @param {Object} data - Bulk work data
   * @param {string} data.work_type - Type of work (cartridge, battery, component, cleaning)
   * @param {Array} data.items - List of items
   * @param {string} data.branch - Branch name
   * @param {string} data.location - Location code
   * @param {string} [data.db_name] - Database name
   * @param {string} [data.cartridge_color] - Cartridge color (for cartridge work)
   * @param {string} [data.component_type] - Component type (for component work)
   * @param {string} [data.component_model] - Component model (for component work)
   * @param {string} [data.employee] - Employee name (for cleaning work)
   * @returns {Promise<Object>} Operation result with success/failed counts
   */
  bulkWork: (data) =>
    apiClient.post('/json/works/bulk', data),

  // ========== Cartridge Database ==========

  /**
   * Get cartridge compatibility for a printer model
   * @param {string} printerModel - Printer model name
   * @returns {Promise<Object>} Compatibility information
   */
  getPrinterCompatibility: (printerModel) =>
    apiClient.get(`/json/cartridges/compatibility/${encodeURIComponent(printerModel)}`),

  /**
   * Get available cartridge colors for a printer model
   * @param {string} printerModel - Printer model name
   * @returns {Promise<Object>} Object with colors array
   */
  getCartridgeColors: (printerModel) =>
    apiClient.get(`/json/cartridges/colors/${encodeURIComponent(printerModel)}`),

  /**
   * Get available component types for a printer model
   * @param {string} printerModel - Printer model name
   * @returns {Promise<Object>} Object with components array
   */
  getPrinterComponents: (printerModel) =>
    apiClient.get(`/json/cartridges/components/${encodeURIComponent(printerModel)}`),

  /**
   * Check if a printer model is color
   * @param {string} printerModel - Printer model name
   * @returns {Promise<Object>} Object with is_color boolean
   */
  isColorPrinter: (printerModel) =>
    apiClient.get(`/json/cartridges/is-color/${encodeURIComponent(printerModel)}`),
};

export default jsonAPI;
