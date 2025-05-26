# Proposed GitHub Issues for Unraid API Repository

This document outlines the GitHub issues that should be created in the [Unraid API repository](https://github.com/unraid/api) to improve Home Assistant integration support.

## Issue Template Format

Each issue should follow the Unraid repository's work intent process and include:
- Clear description of the limitation
- Specific use case for Home Assistant integration
- Examples of needed data/functionality
- Reference to how SSH integration currently handles this

## Priority 1: Critical Missing Features

### 1. User Scripts GraphQL Support

**Title**: Add GraphQL endpoints for User Scripts management

**Description**:
The GraphQL API currently lacks endpoints for managing and monitoring user scripts, which is a critical feature for Home Assistant automation.

**Use Case**:
Home Assistant users need to:
- List available user scripts
- Execute user scripts remotely
- Monitor script execution status
- Get script output/logs

**Current SSH Implementation**:
The SSH-based integration uses commands like:
```bash
/usr/local/emhttp/plugins/user.scripts/scripts/listUserScripts
/usr/local/emhttp/plugins/user.scripts/scripts/start "Script Name"
```

**Proposed GraphQL Schema**:
```graphql
type UserScript {
  id: ID!
  name: String!
  description: String
  running: Boolean!
  lastRun: DateTime
  output: String
}

type Query {
  userScripts: [UserScript!]!
  userScript(id: ID!): UserScript
}

type Mutation {
  executeUserScript(id: ID!): UserScript!
  stopUserScript(id: ID!): UserScript!
}
```

### 2. UPS Monitoring Support

**Title**: Add GraphQL endpoints for UPS monitoring

**Description**:
UPS monitoring is essential for power management automation but is not exposed via GraphQL.

**Use Case**:
Home Assistant users need to:
- Monitor UPS status (online/battery/charging)
- Track battery level and runtime
- Get power consumption data
- Receive alerts for power events

**Current SSH Implementation**:
Uses `upsc` commands and `/var/log/ups` parsing.

**Proposed GraphQL Schema**:
```graphql
type UPS {
  id: ID!
  name: String!
  status: UPSStatus!
  batteryLevel: Float
  runtime: Int
  load: Float
  voltage: Float
  online: Boolean!
}

enum UPSStatus {
  ONLINE
  ON_BATTERY
  CHARGING
  UNKNOWN
}
```

### 3. System Fan Monitoring

**Title**: Add system fan monitoring to GraphQL API

**Description**:
System fan speeds and status are important for thermal monitoring but not available via GraphQL.

**Use Case**:
Monitor system cooling performance and receive alerts for fan failures.

**Current SSH Implementation**:
Parses `/proc/sys/devices/system/cpu/cpu*/thermal_throttle/` and fan control outputs.

## Priority 2: Reliability Improvements

### 4. Improve VM Query Reliability

**Title**: Fix intermittent VM query failures (Enhancement to #1392)

**Description**:
Building on existing issue #1392, VM queries need to be more reliable for Home Assistant automation.

**Specific Requirements**:
- Consistent VM state reporting
- Reliable VM control operations
- Better error messages for failed operations
- Timeout handling for long-running operations

### 5. Fix Memory Value Limitations

**Title**: Support 64-bit memory values in GraphQL API (Enhancement to #1375)

**Description**:
Current 32-bit limitation prevents accurate memory reporting on modern systems.

**Impact on Home Assistant**:
- Incorrect memory usage calculations
- Failed monitoring on systems with >4GB RAM
- Automation triggers based on memory usage fail

### 6. Improve Parity Check Reliability

**Title**: Fix parity check query reliability (Enhancement to #1372)

**Description**:
Parity check monitoring is critical for array health automation.

**Required Improvements**:
- Consistent parity check status reporting
- Progress tracking during operations
- Historical parity check data
- Error reporting for failed checks

## Priority 3: Enhanced Features

### 7. Plugin Management Support

**Title**: Add GraphQL endpoints for plugin management (Enhancement to #1350)

**Description**:
Plugin monitoring and management capabilities for Home Assistant automation.

**Proposed Features**:
- List installed plugins
- Plugin status monitoring
- Plugin update notifications
- Basic plugin control (enable/disable)

### 8. Disk Spin Status Detection

**Title**: Add disk spin status to GraphQL API (Enhancement to #1315)

**Description**:
Disk spin status is important for power management and performance monitoring.

**Use Case**:
- Monitor disk power states
- Optimize array performance
- Power management automation
- Predictive maintenance

### 9. Network Configuration Access

**Title**: Add network configuration to GraphQL API

**Description**:
Network settings and status monitoring for comprehensive system management.

**Proposed Features**:
- Network interface status
- IP configuration
- Network usage statistics
- VPN status (if applicable)

### 10. Enhanced Share Management

**Title**: Expand share management capabilities in GraphQL API

**Description**:
More comprehensive share configuration and monitoring.

**Current Limitations**:
- Limited share metadata
- No share permission management
- Missing share usage analytics

**Proposed Enhancements**:
- Share permissions and security settings
- Usage analytics and trends
- Share health monitoring
- Configuration management

## Priority 4: Developer Experience

### 11. GraphQL Schema Versioning

**Title**: Implement proper GraphQL schema versioning

**Description**:
Breaking changes in the GraphQL schema cause integration failures.

**Requirements**:
- Semantic versioning for schema changes
- Deprecation warnings for removed fields
- Migration guides for breaking changes
- Backward compatibility periods

### 12. Improved Error Handling

**Title**: Standardize GraphQL error responses

**Description**:
Consistent error handling improves integration reliability.

**Requirements**:
- Structured error codes
- Detailed error messages
- Context information for debugging
- Retry guidance for transient errors

## Implementation Strategy

### Phase 1: Critical Features (Immediate)
- User Scripts support
- UPS monitoring
- VM query reliability fixes

### Phase 2: Enhanced Monitoring (Short-term)
- System fan monitoring
- Disk spin status
- Memory value fixes

### Phase 3: Advanced Features (Medium-term)
- Plugin management
- Network configuration
- Enhanced share management

### Phase 4: Developer Experience (Ongoing)
- Schema versioning
- Error handling improvements
- Documentation enhancements

## Success Metrics

- Reduced number of "missing feature" reports
- Improved integration reliability scores
- Increased adoption of GraphQL over SSH integration
- Positive community feedback
- Reduced support burden

## Community Engagement

These issues should be created with:
- Clear technical specifications
- Home Assistant community input
- Unraid developer feedback
- Implementation timeline estimates
- Testing and validation plans
