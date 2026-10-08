from typing import Dict, List, Any
from config.models import ConfigSchema, ConfigType, ConfigScope, RuntimeMutability

DEFAULT_CONFIG_SCHEMAS: List[ConfigSchema] = [
    # --- System Subsystem ---
    ConfigSchema(
        key="system.log_level",
        domain="system",
        data_type=ConfigType.ENUM,
        default_value="INFO",
        scope=ConfigScope.CLUSTER,
        mutability=RuntimeMutability.HOT_RELOAD,
        allowed_values=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        description="Global system log verbosity."
    ),
    ConfigSchema(
        key="system.environment",
        domain="system",
        data_type=ConfigType.ENUM,
        default_value="production",
        scope=ConfigScope.CLUSTER,
        mutability=RuntimeMutability.RESTART_REQUIRED,
        requires_restart=True,
        allowed_values=["development", "staging", "production"],
        description="System environment profile."
    ),
    ConfigSchema(
        key="system.telemetry_enabled",
        domain="system",
        data_type=ConfigType.BOOLEAN,
        default_value=True,
        scope=ConfigScope.CLUSTER,
        mutability=RuntimeMutability.HOT_RELOAD,
        description="Whether runtime telemetry metrics collection is enabled."
    ),
    ConfigSchema(
        key="system.metrics_export_interval_sec",
        domain="system",
        data_type=ConfigType.INTEGER,
        default_value=15,
        scope=ConfigScope.CLUSTER,
        mutability=RuntimeMutability.HOT_RELOAD,
        min_value=1,
        max_value=300,
        unit="seconds",
        description="Interval between metric snapshot exports."
    ),

    # --- Execution Subsystem ---
    ConfigSchema(
        key="execution.max_retries",
        domain="execution",
        data_type=ConfigType.INTEGER,
        default_value=3,
        scope=ConfigScope.CLUSTER,
        mutability=RuntimeMutability.HOT_RELOAD,
        min_value=0,
        max_value=10,
        description="Maximum execution retry attempts per task node."
    ),
    ConfigSchema(
        key="execution.step_timeout_sec",
        domain="execution",
        data_type=ConfigType.FLOAT,
        default_value=30.0,
        scope=ConfigScope.CLUSTER,
        mutability=RuntimeMutability.HOT_RELOAD,
        min_value=1.0,
        max_value=600.0,
        unit="seconds",
        description="Default timeout limit for individual node execution."
    ),
    ConfigSchema(
        key="execution.worker_concurrency",
        domain="execution",
        data_type=ConfigType.INTEGER,
        default_value=4,
        scope=ConfigScope.NODE,
        mutability=RuntimeMutability.HOT_RELOAD,
        min_value=1,
        max_value=32,
        description="Maximum concurrent worker tasks per node."
    ),
    ConfigSchema(
        key="execution.safe_mode",
        domain="execution",
        data_type=ConfigType.BOOLEAN,
        default_value=True,
        scope=ConfigScope.CLUSTER,
        mutability=RuntimeMutability.HOT_RELOAD,
        description="Enforces strict verification and policy guard checks prior to action execution."
    ),

    # --- Vision Subsystem ---
    ConfigSchema(
        key="vision.ocr_confidence_threshold",
        domain="vision",
        data_type=ConfigType.FLOAT,
        default_value=0.6,
        scope=ConfigScope.CLUSTER,
        mutability=RuntimeMutability.HOT_RELOAD,
        min_value=0.1,
        max_value=1.0,
        description="Confidence threshold for optical character recognition detections."
    ),
    ConfigSchema(
        key="vision.capture_fps",
        domain="vision",
        data_type=ConfigType.INTEGER,
        default_value=10,
        scope=ConfigScope.DEVICE,
        mutability=RuntimeMutability.HOT_RELOAD,
        min_value=1,
        max_value=60,
        unit="fps",
        description="Frame capture rate for continuous screen perception."
    ),
    ConfigSchema(
        key="vision.visual_match_tolerance",
        domain="vision",
        data_type=ConfigType.FLOAT,
        default_value=0.85,
        scope=ConfigScope.CLUSTER,
        mutability=RuntimeMutability.HOT_RELOAD,
        min_value=0.5,
        max_value=1.0,
        description="Similarity tolerance for template and visual grounding matches."
    ),

    # --- Browser Subsystem ---
    ConfigSchema(
        key="browser.headless",
        domain="browser",
        data_type=ConfigType.BOOLEAN,
        default_value=True,
        scope=ConfigScope.NODE,
        mutability=RuntimeMutability.RESTART_REQUIRED,
        requires_restart=True,
        description="Whether Playwright browser instances run in headless mode."
    ),
    ConfigSchema(
        key="browser.navigation_timeout_sec",
        domain="browser",
        data_type=ConfigType.FLOAT,
        default_value=25.0,
        scope=ConfigScope.CLUSTER,
        mutability=RuntimeMutability.HOT_RELOAD,
        min_value=2.0,
        max_value=120.0,
        unit="seconds",
        description="Timeout for page navigation and load events."
    ),
    ConfigSchema(
        key="browser.viewport_width",
        domain="browser",
        data_type=ConfigType.INTEGER,
        default_value=1280,
        scope=ConfigScope.CLUSTER,
        mutability=RuntimeMutability.HOT_RELOAD,
        min_value=320,
        max_value=3840,
        unit="pixels",
        description="Default browser viewport width."
    ),
    ConfigSchema(
        key="browser.viewport_height",
        domain="browser",
        data_type=ConfigType.INTEGER,
        default_value=720,
        scope=ConfigScope.CLUSTER,
        mutability=RuntimeMutability.HOT_RELOAD,
        min_value=240,
        max_value=2160,
        unit="pixels",
        description="Default browser viewport height."
    ),

    # --- Mesh Subsystem ---
    ConfigSchema(
        key="mesh.heartbeat_interval_sec",
        domain="mesh",
        data_type=ConfigType.FLOAT,
        default_value=2.0,
        scope=ConfigScope.CLUSTER,
        mutability=RuntimeMutability.HOT_RELOAD,
        min_value=0.5,
        max_value=30.0,
        unit="seconds",
        description="Heartbeat ping frequency between mesh nodes."
    ),
    ConfigSchema(
        key="mesh.discovery_sweep_sec",
        domain="mesh",
        data_type=ConfigType.INTEGER,
        default_value=10,
        scope=ConfigScope.CLUSTER,
        mutability=RuntimeMutability.HOT_RELOAD,
        min_value=2,
        max_value=60,
        unit="seconds",
        description="Interval for active discovery broadcast on the local network."
    ),
    ConfigSchema(
        key="mesh.max_nodes",
        domain="mesh",
        data_type=ConfigType.INTEGER,
        default_value=16,
        scope=ConfigScope.CLUSTER,
        mutability=RuntimeMutability.HOT_RELOAD,
        min_value=1,
        max_value=128,
        description="Upper bound of allowed active nodes participating in mesh."
    ),

    # --- Coordination Subsystem ---
    ConfigSchema(
        key="coordination.election_timeout_sec",
        domain="coordination",
        data_type=ConfigType.FLOAT,
        default_value=5.0,
        scope=ConfigScope.CLUSTER,
        mutability=RuntimeMutability.HOT_RELOAD,
        min_value=1.0,
        max_value=30.0,
        unit="seconds",
        description="Timeout for leader election before assuming partition or failure."
    ),
    ConfigSchema(
        key="coordination.lease_ttl_sec",
        domain="coordination",
        data_type=ConfigType.FLOAT,
        default_value=10.0,
        scope=ConfigScope.CLUSTER,
        mutability=RuntimeMutability.HOT_RELOAD,
        min_value=2.0,
        max_value=60.0,
        unit="seconds",
        dependencies=["coordination.heartbeat_period_sec"],
        description="Lease time-to-live for leader and ownership locks."
    ),
    ConfigSchema(
        key="coordination.heartbeat_period_sec",
        domain="coordination",
        data_type=ConfigType.FLOAT,
        default_value=2.0,
        scope=ConfigScope.CLUSTER,
        mutability=RuntimeMutability.HOT_RELOAD,
        min_value=0.5,
        max_value=10.0,
        unit="seconds",
        description="Leader lease renewal interval (must be less than lease_ttl_sec)."
    ),

    # --- Replication Subsystem ---
    ConfigSchema(
        key="replication.sync_interval_sec",
        domain="replication",
        data_type=ConfigType.FLOAT,
        default_value=1.0,
        scope=ConfigScope.CLUSTER,
        mutability=RuntimeMutability.HOT_RELOAD,
        min_value=0.1,
        max_value=10.0,
        unit="seconds",
        description="Interval for background state delta synchronization."
    ),
    ConfigSchema(
        key="replication.max_batch_size",
        domain="replication",
        data_type=ConfigType.INTEGER,
        default_value=50,
        scope=ConfigScope.CLUSTER,
        mutability=RuntimeMutability.HOT_RELOAD,
        min_value=5,
        max_value=500,
        description="Maximum number of state deltas packaged into a replication batch."
    ),
    ConfigSchema(
        key="replication.anti_entropy_sweep_sec",
        domain="replication",
        data_type=ConfigType.INTEGER,
        default_value=30,
        scope=ConfigScope.CLUSTER,
        mutability=RuntimeMutability.HOT_RELOAD,
        min_value=5,
        max_value=300,
        unit="seconds",
        description="Periodic anti-entropy verification interval."
    ),

    # --- Scheduler Subsystem ---
    ConfigSchema(
        key="scheduler.algorithm",
        domain="scheduler",
        data_type=ConfigType.ENUM,
        default_value="PRIORITY_WEIGHTED",
        scope=ConfigScope.CLUSTER,
        mutability=RuntimeMutability.HOT_RELOAD,
        allowed_values=["FIFO", "PRIORITY_WEIGHTED", "FAIR_SHARE"],
        description="Scheduling algorithm for queuing and dispatching runnable tasks."
    ),
    ConfigSchema(
        key="scheduler.max_concurrent_tasks",
        domain="scheduler",
        data_type=ConfigType.INTEGER,
        default_value=8,
        scope=ConfigScope.CLUSTER,
        mutability=RuntimeMutability.HOT_RELOAD,
        min_value=1,
        max_value=64,
        description="Cluster-wide maximum concurrent active tasks."
    ),
    ConfigSchema(
        key="scheduler.preemption_enabled",
        domain="scheduler",
        data_type=ConfigType.BOOLEAN,
        default_value=True,
        scope=ConfigScope.CLUSTER,
        mutability=RuntimeMutability.HOT_RELOAD,
        description="Whether high-priority tasks are allowed to preempt lower-priority tasks."
    ),

    # --- Supervisor Subsystem ---
    ConfigSchema(
        key="supervisor.health_eval_interval_sec",
        domain="supervisor",
        data_type=ConfigType.FLOAT,
        default_value=3.0,
        scope=ConfigScope.CLUSTER,
        mutability=RuntimeMutability.HOT_RELOAD,
        min_value=0.5,
        max_value=30.0,
        unit="seconds",
        description="Frequency of supervisor progress and health assessments."
    ),
    ConfigSchema(
        key="supervisor.max_consecutive_anomalies",
        domain="supervisor",
        data_type=ConfigType.INTEGER,
        default_value=5,
        scope=ConfigScope.CLUSTER,
        mutability=RuntimeMutability.HOT_RELOAD,
        min_value=1,
        max_value=20,
        description="Consecutive anomalies allowed before supervisor halts or triggers safe replan."
    ),

    # --- Approval Subsystem ---
    ConfigSchema(
        key="approval.default_timeout_sec",
        domain="approval",
        data_type=ConfigType.FLOAT,
        default_value=300.0,
        scope=ConfigScope.CLUSTER,
        mutability=RuntimeMutability.HOT_RELOAD,
        min_value=10.0,
        max_value=3600.0,
        unit="seconds",
        description="Default timeout period before pending human approval expires."
    ),
    ConfigSchema(
        key="approval.auto_reject_on_expiry",
        domain="approval",
        data_type=ConfigType.BOOLEAN,
        default_value=True,
        scope=ConfigScope.CLUSTER,
        mutability=RuntimeMutability.HOT_RELOAD,
        description="Whether expired approval requests default to REJECTED."
    ),

    # --- Credentials & Security References ---
    ConfigSchema(
        key="security.api_auth_token_ref",
        domain="security",
        data_type=ConfigType.SECRET_REF,
        default_value="secret://vault/api_auth_token",
        scope=ConfigScope.CLUSTER,
        mutability=RuntimeMutability.HOT_RELOAD,
        is_secret=True,
        description="Reference URI to external vault or secure enclave for API auth token."
    ),

    # --- Video Studio Optional Subsystem (Module 0) ---
    ConfigSchema(
        key="video_studio.enabled",
        domain="video_studio",
        data_type=ConfigType.BOOLEAN,
        default_value=False,
        scope=ConfigScope.CLUSTER,
        mutability=RuntimeMutability.HOT_RELOAD,
        description="Master enablement switch for optional OMNIA Video Studio subsystem."
    ),
    ConfigSchema(
        key="video_studio.experimental",
        domain="video_studio",
        data_type=ConfigType.BOOLEAN,
        default_value=False,
        scope=ConfigScope.CLUSTER,
        mutability=RuntimeMutability.HOT_RELOAD,
        description="Allows experimental video editing capabilities and developmental tools."
    ),
    ConfigSchema(
        key="video_studio.max_concurrent_jobs",
        domain="video_studio",
        data_type=ConfigType.INTEGER,
        default_value=2,
        scope=ConfigScope.NODE,
        mutability=RuntimeMutability.HOT_RELOAD,
        min_value=1,
        max_value=16,
        description="Maximum concurrent video processing and rendering jobs per node."
    ),
    ConfigSchema(
        key="video_studio.cache_location",
        domain="video_studio",
        data_type=ConfigType.STRING,
        default_value="./data/video_studio/cache",
        scope=ConfigScope.NODE,
        mutability=RuntimeMutability.HOT_RELOAD,
        description="Filesystem location for transient video waveforms, peak files, and timeline cache."
    ),
    ConfigSchema(
        key="video_studio.proxy_location",
        domain="video_studio",
        data_type=ConfigType.STRING,
        default_value="./data/video_studio/proxies",
        scope=ConfigScope.NODE,
        mutability=RuntimeMutability.HOT_RELOAD,
        description="Filesystem location for generated low-resolution editing proxies."
    ),
    ConfigSchema(
        key="video_studio.render_location",
        domain="video_studio",
        data_type=ConfigType.STRING,
        default_value="./data/video_studio/renders",
        scope=ConfigScope.NODE,
        mutability=RuntimeMutability.HOT_RELOAD,
        description="Filesystem location for intermediate render frames and final project exports."
    ),
    ConfigSchema(
        key="video_studio.gpu_acceleration",
        domain="video_studio",
        data_type=ConfigType.BOOLEAN,
        default_value=True,
        scope=ConfigScope.NODE,
        mutability=RuntimeMutability.HOT_RELOAD,
        description="Whether hardware GPU acceleration is requested for encode/decode/compositing."
    ),
    ConfigSchema(
        key="video_studio.ai_enabled",
        domain="video_studio",
        data_type=ConfigType.BOOLEAN,
        default_value=True,
        scope=ConfigScope.CLUSTER,
        mutability=RuntimeMutability.HOT_RELOAD,
        description="Enables AI-driven video capabilities (transcription, auto-reframe, isolation)."
    ),
    ConfigSchema(
        key="video_studio.extensions_enabled",
        domain="video_studio",
        data_type=ConfigType.BOOLEAN,
        default_value=True,
        scope=ConfigScope.CLUSTER,
        mutability=RuntimeMutability.HOT_RELOAD,
        description="Enables dynamic Video Studio plugin and capability extensions."
    )
]

def get_default_schemas_dict() -> Dict[str, ConfigSchema]:
    return {s.key: s for s in DEFAULT_CONFIG_SCHEMAS}

def get_default_values_dict() -> Dict[str, Any]:
    return {s.key: s.default_value for s in DEFAULT_CONFIG_SCHEMAS}
