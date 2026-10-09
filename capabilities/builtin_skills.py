import logging
from typing import Dict, Any

from capabilities.models import (
    Capability,
    CapabilityProvider,
    CapabilityCategory,
    CapabilityHealth,
    RiskLevel,
    SideEffectType,
    IdempotencyType,
    ReversibilityType,
    VerificationContract
)
from capabilities.registry import capability_registry, CapabilityRegistry

logger = logging.getLogger("Omnia.Capabilities.BuiltinSkills")

def register_all_builtin_capabilities(registry: CapabilityRegistry = capability_registry):
    """Registers all authoritative, production capabilities supported by the Omnia runtime."""

    # =========================================================
    # 1. BROWSER CAPABILITIES
    # =========================================================
    registry.register_capability(Capability(
        id="browser.navigate",
        name="Browser URL Navigation",
        description="Navigates the autonomous Playwright browser instance to a specified URL",
        version="1.0.0",
        category=CapabilityCategory.BROWSER,
        input_schema={"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
        output_schema={"type": "object", "properties": {"current_url": {"type": "string"}, "title": {"type": "string"}}},
        environment="browser",
        platforms=["windows", "linux", "macos"],
        required_resources=["browser:session"],
        required_permissions=["network:http", "browser:control"],
        risk_level=RiskLevel.READ_ONLY,
        side_effects=[SideEffectType.READ, SideEffectType.NETWORK],
        reversible=ReversibilityType.REVERSIBLE,
        idempotent=IdempotencyType.IDEMPOTENT,
        verification_contract=VerificationContract(mechanism="DOM_URL_MATCH", target_expression="window.location.href"),
        default_timeout_sec=30.0,
        health=CapabilityHealth.HEALTHY
    ))
    registry.register_provider(CapabilityProvider(
        provider_id="provider.browser.playwright.local",
        capability_id="browser.navigate",
        implementation_ref="browser_driver.browser_driver.navigate_to",
        version="1.0.0",
        priority=10,
        health=CapabilityHealth.HEALTHY,
        latency_ms=250.0
    ))

    registry.register_capability(Capability(
        id="browser.execute_task",
        name="Browser Autonomous Web Task",
        description="Performs an end-to-end autonomous DOM interaction flow to accomplish a goal",
        version="1.0.0",
        category=CapabilityCategory.BROWSER,
        input_schema={"type": "object", "properties": {"url": {"type": "string"}, "objective": {"type": "string"}}, "required": ["url", "objective"]},
        output_schema={"type": "object", "properties": {"task_result": {"type": "string"}}},
        environment="browser",
        platforms=["windows", "linux", "macos"],
        required_resources=["browser:session"],
        required_permissions=["network:http", "browser:control"],
        risk_level=RiskLevel.MODERATE_RISK,
        side_effects=[SideEffectType.READ, SideEffectType.WRITE, SideEffectType.NETWORK],
        reversible=ReversibilityType.CONDITIONALLY_REVERSIBLE,
        idempotent=IdempotencyType.NON_IDEMPOTENT,
        verification_contract=VerificationContract(mechanism="DOM_STATE_CHANGE"),
        default_timeout_sec=45.0,
        dependencies=["browser.navigate"],
        health=CapabilityHealth.HEALTHY
    ))
    registry.register_provider(CapabilityProvider(
        provider_id="provider.browser.agent.local",
        capability_id="browser.execute_task",
        implementation_ref="browser_agent.browser_agent.run_task",
        version="1.0.0",
        priority=10,
        health=CapabilityHealth.HEALTHY,
        latency_ms=1200.0
    ))

    # =========================================================
    # 2. VISION CAPABILITIES
    # =========================================================
    registry.register_capability(Capability(
        id="vision.capture_screen",
        name="Screen Frame Capture",
        description="Captures linear raw pixels and frame buffer of host desktop or active mobile screen",
        version="1.0.0",
        category=CapabilityCategory.VISION,
        input_schema={"type": "object", "properties": {"source": {"type": "string", "enum": ["desktop", "android"]}}},
        output_schema={"type": "object", "properties": {"frame_id": {"type": "string"}, "width": {"type": "integer"}}},
        environment="desktop",
        platforms=["windows", "linux", "macos", "android"],
        required_resources=["display:screen"],
        required_permissions=["system:screen_capture"],
        risk_level=RiskLevel.READ_ONLY,
        side_effects=[SideEffectType.READ],
        reversible=ReversibilityType.REVERSIBLE,
        idempotent=IdempotencyType.IDEMPOTENT,
        verification_contract=VerificationContract(mechanism="FRAME_INTEGRITY"),
        default_timeout_sec=10.0,
        health=CapabilityHealth.HEALTHY
    ))
    registry.register_provider(CapabilityProvider(
        provider_id="provider.vision.capture.local",
        capability_id="vision.capture_screen",
        implementation_ref="vision.capture.screen_capture_engine.capture_desktop",
        version="1.0.0",
        priority=10,
        health=CapabilityHealth.HEALTHY,
        latency_ms=65.0
    ))

    registry.register_capability(Capability(
        id="vision.find_element",
        name="Multimodal Visual Grounding",
        description="Performs OCR and semantic visual grounding to locate coordinates of text or interactive UI elements",
        version="1.0.0",
        category=CapabilityCategory.VISION,
        input_schema={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        output_schema={"type": "object", "properties": {"box_2d": {"type": "array"}, "confidence": {"type": "number"}}},
        environment="desktop",
        platforms=["windows", "linux", "macos", "android"],
        required_resources=[],
        required_permissions=[],
        risk_level=RiskLevel.READ_ONLY,
        side_effects=[SideEffectType.READ],
        reversible=ReversibilityType.REVERSIBLE,
        idempotent=IdempotencyType.IDEMPOTENT,
        verification_contract=VerificationContract(mechanism="CONFIDENCE_THRESHOLD", expected_state="0.6"),
        default_timeout_sec=15.0,
        dependencies=["vision.capture_screen"],
        health=CapabilityHealth.HEALTHY
    ))
    registry.register_provider(CapabilityProvider(
        provider_id="provider.vision.rapidocr.local",
        capability_id="vision.find_element",
        implementation_ref="vision.grounding.visual_grounding_engine.ground_target",
        version="1.0.0",
        priority=10,
        health=CapabilityHealth.HEALTHY,
        latency_ms=180.0
    ))

    registry.register_capability(Capability(
        id="vision.verify_state",
        name="Visual State Verification",
        description="Verifies visual presence of text, dialogs, or UI changes using diffing and OCR",
        version="1.0.0",
        category=CapabilityCategory.VISION,
        input_schema={"type": "object", "properties": {"expected_text": {"type": "string"}}, "required": ["expected_text"]},
        output_schema={"type": "object", "properties": {"verified": {"type": "boolean"}, "score": {"type": "number"}}},
        environment="desktop",
        platforms=["windows", "linux", "macos", "android"],
        required_resources=[],
        required_permissions=[],
        risk_level=RiskLevel.READ_ONLY,
        side_effects=[SideEffectType.READ],
        reversible=ReversibilityType.REVERSIBLE,
        idempotent=IdempotencyType.IDEMPOTENT,
        verification_contract=VerificationContract(mechanism="OCR_TEXT_MATCH"),
        default_timeout_sec=15.0,
        dependencies=["vision.capture_screen"],
        health=CapabilityHealth.HEALTHY
    ))
    registry.register_provider(CapabilityProvider(
        provider_id="provider.vision.verifier.local",
        capability_id="vision.verify_state",
        implementation_ref="vision.verification.visual_verification_engine.verify_state",
        version="1.0.0",
        priority=10,
        health=CapabilityHealth.HEALTHY,
        latency_ms=120.0
    ))

    # =========================================================
    # 3. DEVICE & ANDROID CAPABILITIES
    # =========================================================
    registry.register_capability(Capability(
        id="device.android.unlock",
        name="Android Mesh Screen Unlock",
        description="Wakes and dismisses lockscreen PIN or swipe across connected Android ADB devices",
        version="1.0.0",
        category=CapabilityCategory.DEVICE,
        input_schema={"type": "object", "properties": {}},
        output_schema={"type": "object", "properties": {"devices_unlocked": {"type": "integer"}}},
        environment="android",
        platforms=["android"],
        required_resources=["adb:connection"],
        required_permissions=["device:adb_control"],
        risk_level=RiskLevel.LOW_RISK,
        side_effects=[SideEffectType.DEVICE_CONTROL],
        reversible=ReversibilityType.REVERSIBLE,
        idempotent=IdempotencyType.IDEMPOTENT,
        verification_contract=VerificationContract(mechanism="DEVICE_WAKE_VERIFICATION"),
        default_timeout_sec=10.0,
        health=CapabilityHealth.UNKNOWN
    ))
    registry.register_provider(CapabilityProvider(
        provider_id="provider.device.adb.local",
        capability_id="device.android.unlock",
        implementation_ref="device_controller.DeviceController.wake_and_unlock_mesh",
        version="1.0.0",
        priority=10,
        health=CapabilityHealth.UNKNOWN,
        latency_ms=300.0
    ))

    registry.register_capability(Capability(
        id="device.android.youtube",
        name="Android YouTube Playback",
        description="Launches target YouTube video via explicit intent across Android devices",
        version="1.0.0",
        category=CapabilityCategory.DEVICE,
        input_schema={"type": "object", "properties": {"video_id": {"type": "string"}}, "required": ["video_id"]},
        output_schema={"type": "object", "properties": {"dispatched_count": {"type": "integer"}}},
        environment="android",
        platforms=["android"],
        required_resources=["adb:connection"],
        required_permissions=["device:adb_control", "network:internet"],
        risk_level=RiskLevel.LOW_RISK,
        side_effects=[SideEffectType.DEVICE_CONTROL, SideEffectType.NETWORK],
        reversible=ReversibilityType.REVERSIBLE,
        idempotent=IdempotencyType.IDEMPOTENT,
        verification_contract=VerificationContract(mechanism="INTENT_DISPATCH_CONFIRMATION"),
        default_timeout_sec=15.0,
        dependencies=["device.android.unlock"],
        health=CapabilityHealth.UNKNOWN
    ))
    registry.register_provider(CapabilityProvider(
        provider_id="provider.device.adb.local",
        capability_id="device.android.youtube",
        implementation_ref="device_controller.DeviceController.launch_youtube",
        version="1.0.0",
        priority=10,
        health=CapabilityHealth.UNKNOWN,
        latency_ms=450.0
    ))

    registry.register_capability(Capability(
        id="device.android.shell",
        name="Android ADB Shell Broadcast",
        description="Executes a shell command across connected ADB devices subject to safety policy inspection",
        version="1.0.0",
        category=CapabilityCategory.DEVICE,
        input_schema={"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]},
        output_schema={"type": "object", "properties": {"exit_codes": {"type": "object"}}},
        environment="android",
        platforms=["android"],
        required_resources=["adb:connection"],
        required_permissions=["device:adb_control", "system:shell"],
        risk_level=RiskLevel.HIGH_RISK,
        side_effects=[SideEffectType.DEVICE_CONTROL, SideEffectType.WRITE],
        reversible=ReversibilityType.POTENTIALLY_IRREVERSIBLE,
        idempotent=IdempotencyType.CONDITIONALLY_IDEMPOTENT,
        verification_contract=VerificationContract(mechanism="PROCESS_EXIT_ZERO"),
        default_timeout_sec=20.0,
        health=CapabilityHealth.UNKNOWN
    ))
    registry.register_provider(CapabilityProvider(
        provider_id="provider.device.adb.local",
        capability_id="device.android.shell",
        implementation_ref="device_controller.DeviceController.broadcast_shell",
        version="1.0.0",
        priority=10,
        health=CapabilityHealth.UNKNOWN,
        latency_ms=150.0
    ))

    # =========================================================
    # 4. VOICE & TTS CAPABILITIES
    # =========================================================
    registry.register_capability(Capability(
        id="voice.speak",
        name="Neural Text-to-Speech Output",
        description="Synthesizes and speaks phrases aloud using Piper/EdgeTTS or audio playback queues",
        version="1.0.0",
        category=CapabilityCategory.VOICE,
        input_schema={"type": "object", "properties": {"phrase": {"type": "string"}}, "required": ["phrase"]},
        output_schema={"type": "object", "properties": {"spoken": {"type": "boolean"}}},
        environment="desktop",
        platforms=["windows", "linux", "macos"],
        required_resources=["audio:output"],
        required_permissions=["system:audio_output"],
        risk_level=RiskLevel.READ_ONLY,
        side_effects=[SideEffectType.DEVICE_CONTROL],
        reversible=ReversibilityType.REVERSIBLE,
        idempotent=IdempotencyType.IDEMPOTENT,
        verification_contract=VerificationContract(mechanism="AUDIO_PLAYBACK_COMPLETE"),
        default_timeout_sec=15.0,
        health=CapabilityHealth.HEALTHY
    ))
    registry.register_provider(CapabilityProvider(
        provider_id="provider.voice.local",
        capability_id="voice.speak",
        implementation_ref="audio_synthesizer.synthesize_speech",
        version="1.0.0",
        priority=10,
        health=CapabilityHealth.HEALTHY,
        latency_ms=100.0
    ))

    # Fallback provider for cloud/remote speech
    registry.register_provider(CapabilityProvider(
        provider_id="provider.voice.remote_edge",
        capability_id="voice.speak",
        implementation_ref="voice_pipeline.fallback_speak",
        version="1.0.0",
        priority=20,
        health=CapabilityHealth.HEALTHY,
        latency_ms=450.0
    ))

    # =========================================================
    # 5. MEMORY CAPABILITIES
    # =========================================================
    registry.register_capability(Capability(
        id="memory.search_context",
        name="Vector Memory Semantic Search",
        description="Searches local vector embeddings database for contextual user memories and interactions",
        version="1.0.0",
        category=CapabilityCategory.MEMORY,
        input_schema={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        output_schema={"type": "object", "properties": {"documents": {"type": "array"}}},
        environment="local",
        platforms=["windows", "linux", "macos"],
        required_resources=["memory:db"],
        required_permissions=[],
        risk_level=RiskLevel.READ_ONLY,
        side_effects=[SideEffectType.READ],
        reversible=ReversibilityType.REVERSIBLE,
        idempotent=IdempotencyType.IDEMPOTENT,
        verification_contract=VerificationContract(mechanism="MEMORY_QUERY_COMPLETED"),
        default_timeout_sec=5.0,
        health=CapabilityHealth.HEALTHY
    ))
    registry.register_provider(CapabilityProvider(
        provider_id="provider.memory.chroma.local",
        capability_id="memory.search_context",
        implementation_ref="memory_engine.memory.search",
        version="1.0.0",
        priority=10,
        health=CapabilityHealth.HEALTHY,
        latency_ms=15.0
    ))

    # =========================================================
    # 6. MESH & DISTRIBUTED CAPABILITIES
    # =========================================================
    registry.register_capability(Capability(
        id="mesh.execute_command",
        name="Distributed Mesh Remote Command",
        description="Dispatches a shell or orchestration command across peer nodes on the local mesh",
        version="1.0.0",
        category=CapabilityCategory.MESH,
        input_schema={"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]},
        output_schema={"type": "object", "properties": {"node_responses": {"type": "object"}}},
        environment="mesh",
        platforms=["windows", "linux"],
        required_resources=["mesh:network"],
        required_permissions=["network:lan", "system:remote_exec"],
        risk_level=RiskLevel.HIGH_RISK,
        side_effects=[SideEffectType.NETWORK, SideEffectType.WRITE],
        reversible=ReversibilityType.POTENTIALLY_IRREVERSIBLE,
        idempotent=IdempotencyType.NON_IDEMPOTENT,
        verification_contract=VerificationContract(mechanism="PEER_ACK_RECEIVED"),
        default_timeout_sec=25.0,
        health=CapabilityHealth.HEALTHY
    ))
    registry.register_provider(CapabilityProvider(
        provider_id="provider.mesh.lan.multicast",
        capability_id="mesh.execute_command",
        implementation_ref="mesh_replicator.broadcast_event",
        version="1.0.0",
        priority=10,
        health=CapabilityHealth.HEALTHY,
        latency_ms=50.0
    ))

    # =========================================================
    # 7. TELEPHONY CAPABILITIES
    # =========================================================
    registry.register_capability(Capability(
        id="telephony.stream_audio",
        name="Telephony Full-Duplex Voice Stream",
        description="Routes audio streams bi-directionally over active SIP/Twilio telephony WebSockets",
        version="1.0.0",
        category=CapabilityCategory.TELEPHONY,
        input_schema={"type": "object", "properties": {"call_sid": {"type": "string"}}, "required": ["call_sid"]},
        output_schema={"type": "object", "properties": {"stream_status": {"type": "string"}}},
        environment="network",
        platforms=["windows", "linux", "macos"],
        required_resources=["telephony:socket"],
        required_permissions=["network:telephony", "audio:streaming"],
        risk_level=RiskLevel.MODERATE_RISK,
        side_effects=[SideEffectType.EXTERNAL_COMMUNICATION, SideEffectType.NETWORK],
        reversible=ReversibilityType.REVERSIBLE,
        idempotent=IdempotencyType.NON_IDEMPOTENT,
        verification_contract=VerificationContract(mechanism="SOCKET_STREAM_ESTABLISHED"),
        default_timeout_sec=30.0,
        health=CapabilityHealth.HEALTHY
    ))
    registry.register_provider(CapabilityProvider(
        provider_id="provider.telephony.fastapi.gateway",
        capability_id="telephony.stream_audio",
        implementation_ref="telephony_gateway.handle_stream",
        version="1.0.0",
        priority=10,
        health=CapabilityHealth.HEALTHY,
        latency_ms=80.0
    ))
    # =========================================================
    # 8. VIDEO STUDIO CAPABILITIES (Module 0 Foundation)
    # =========================================================
    registry.register_capability(Capability(
        id="video_studio.get_status",
        name="Video Studio Subsystem Status",
        description="Queries operational readiness, hardware compute, and lifecycle state of optional Video Studio",
        version="0.1.0",
        category=CapabilityCategory.VIDEO_STUDIO,
        input_schema={"type": "object", "properties": {}},
        output_schema={"type": "object", "properties": {"state": {"type": "string"}, "is_enabled": {"type": "boolean"}}},
        environment="local",
        platforms=["windows", "linux", "macos"],
        required_resources=[],
        required_permissions=[],
        risk_level=RiskLevel.READ_ONLY,
        side_effects=[SideEffectType.READ],
        reversible=ReversibilityType.REVERSIBLE,
        idempotent=IdempotencyType.IDEMPOTENT,
        verification_contract=VerificationContract(mechanism="STATUS_QUERY_SUCCESS"),
        default_timeout_sec=5.0,
        health=CapabilityHealth.HEALTHY
    ))
    registry.register_provider(CapabilityProvider(
        provider_id="provider.video_studio.subsystem",
        capability_id="video_studio.get_status",
        implementation_ref="video_studio.service.video_studio_service.get_status_summary",
        version="0.1.0",
        priority=10,
        health=CapabilityHealth.HEALTHY,
        latency_ms=5.0
    ))

    logger.info(f"Registered {len(registry.list_capabilities())} built-in capabilities into registry.")
