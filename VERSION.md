# Version History

## Version 1.0 - Initial Release

**Release Date:** January 2026

### Description
ProAutomation Studio is a real-time HMI (Human Machine Interface) application for monitoring and visualizing industrial automation data. The application provides:

- **Real-time PLC Communication**: Direct connection to Siemens S7-1500 PLCs via Snap7 protocol
- **Dynamic Data Visualization**: Interactive graphs with support for multiple variables, dual Y-axes, and XY plotting
- **Data Logging**: Automatic storage of PLC data to DuckDB database for historical analysis
- **Recipe Parameter Monitoring**: Separate tracking and display of recipe parameters
- **Communication Status**: Real-time monitoring of connection status, read counts, and error tracking
- **Configurable Communication Speed**: Adjustable cycle time for PLC data acquisition

### Key Features
- Multi-graph support with independent configuration
- Collapsible communication information panel
- Configurable axis ranges (auto or manual min/max)
- Hover tooltips with detailed variable information
- Recipe parameter display in graph tooltips
- Dark theme UI optimized for industrial environments

### Technical Stack
- **UI Framework**: PySide6 (Qt6)
- **Plotting**: PyQtGraph
- **PLC Communication**: python-snap7
- **Database**: DuckDB
- **Python**: 3.12+
