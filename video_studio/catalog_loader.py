"""OMNIA Video Studio — Module 1: Catalog Ingest & Auto-Populator.

Populates the VideoStudioCapabilityRegistry with all planned roadmap capabilities,
ensuring:
1. Every capability has standard dot-notation namespace (e.g. "video.timeline.multitrack").
2. Explicit implementation_state is PLANNED (NOT falsely marked as implemented).
3. Declares appropriate hardware, platform, AI, and dependency constraints.
4. Distinguishes enabled configuration from real runtime availability.
"""

from typing import Dict, List
from video_studio.registry_models import (
    VideoStudioCategory,
    ImplementationState,
    VideoStudioCapabilityDescriptor,
    CapabilityDependency,
    HardwareRequirements,
    PlatformRequirements,
    AIRequirements,
    AccelerationAPI,
)
from video_studio.registry import VideoStudioCapabilityRegistry

def populate_roadmap_capabilities(registry: VideoStudioCapabilityRegistry) -> int:
    """Populates the complete roadmap catalog into the capability registry."""
    count = 0

    capabilities_data = [
        # --- 1. EDITING / TIMELINE ---
        VideoStudioCapabilityDescriptor(
            id="video.timeline.multitrack",
            name="Multi-track Timeline Editing",
            description="Parallel multi-track composition across arbitrary video, audio, and graphics layers.",
            category=VideoStudioCategory.EDITING,
            implementation_state=ImplementationState.PLANNED,
            tags=["editing", "timeline", "core"],
            hardware_requirements=HardwareRequirements(min_ram_mb=4096, recommended_ram_mb=8192)
        ),
        VideoStudioCapabilityDescriptor(
            id="video.timeline.ripple_edit",
            name="Ripple Edit Tool",
            description="Automatic downstream clip shifting on head/tail trim or clip deletion.",
            category=VideoStudioCategory.EDITING,
            implementation_state=ImplementationState.PLANNED,
            dependencies=[CapabilityDependency("video.timeline.multitrack")],
            tags=["editing", "trim"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.timeline.rolling_edit",
            name="Rolling Edit Tool",
            description="Dual-edit boundary trimming that preserves total timeline duration.",
            category=VideoStudioCategory.EDITING,
            implementation_state=ImplementationState.PLANNED,
            dependencies=[CapabilityDependency("video.timeline.multitrack")],
            tags=["editing", "trim"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.timeline.slip",
            name="Slip Edit Tool",
            description="Shift source in/out points while holding timeline duration and position.",
            category=VideoStudioCategory.EDITING,
            implementation_state=ImplementationState.PLANNED,
            dependencies=[CapabilityDependency("video.timeline.multitrack")],
            tags=["editing", "trim"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.timeline.slide",
            name="Slide Edit Tool",
            description="Shift timeline clip position while rolling adjacent heads and tails.",
            category=VideoStudioCategory.EDITING,
            implementation_state=ImplementationState.PLANNED,
            dependencies=[CapabilityDependency("video.timeline.multitrack")],
            tags=["editing", "trim"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.timeline.razor",
            name="Razor / Blade Tool",
            description="Frame-accurate split cutting across active or targeted tracks.",
            category=VideoStudioCategory.EDITING,
            implementation_state=ImplementationState.PLANNED,
            dependencies=[CapabilityDependency("video.timeline.multitrack")],
            tags=["editing", "cut"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.timeline.freeze_frame",
            name="Freeze Frame Hold",
            description="Static frame hold generation with customizable duration.",
            category=VideoStudioCategory.EDITING,
            implementation_state=ImplementationState.PLANNED,
            dependencies=[CapabilityDependency("video.timeline.multitrack")],
            tags=["editing", "freeze"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.timeline.reverse",
            name="Reverse Clip Playback",
            description="Bidirectional timeline clip playback and frame inversion.",
            category=VideoStudioCategory.EDITING,
            implementation_state=ImplementationState.PLANNED,
            dependencies=[CapabilityDependency("video.timeline.multitrack")],
            tags=["editing", "speed"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.timeline.nested_sequences",
            name="Nested Sequences & Compound Clips",
            description="Hierarchical sequence encapsulation and compound clip re-use.",
            category=VideoStudioCategory.EDITING,
            implementation_state=ImplementationState.PLANNED,
            dependencies=[CapabilityDependency("video.timeline.multitrack")],
            tags=["editing", "sequences"]
        ),

        # --- 2. MOTION ---
        VideoStudioCapabilityDescriptor(
            id="video.motion.keyframes",
            name="Parametric Keyframe Engine",
            description="Sub-frame parametric parameter automation and interpolation.",
            category=VideoStudioCategory.MOTION,
            implementation_state=ImplementationState.PLANNED,
            tags=["motion", "animation"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.motion.bezier",
            name="Bezier Velocity Curves",
            description="Cubic and ease-in/ease-out velocity curve shaping.",
            category=VideoStudioCategory.MOTION,
            implementation_state=ImplementationState.PLANNED,
            dependencies=[CapabilityDependency("video.motion.keyframes")],
            tags=["motion", "curves"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.motion.speed_ramping",
            name="Speed Ramping",
            description="Variable time-remapping curves with motion interpolation.",
            category=VideoStudioCategory.MOTION,
            implementation_state=ImplementationState.PLANNED,
            dependencies=[CapabilityDependency("video.motion.keyframes")],
            tags=["motion", "speed"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.motion.camera_shake",
            name="Procedural Camera Shake",
            description="Simulated handheld organic motion and perturbation.",
            category=VideoStudioCategory.MOTION,
            implementation_state=ImplementationState.PLANNED,
            dependencies=[CapabilityDependency("video.motion.keyframes")],
            tags=["motion", "vfx"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.motion.wiggle",
            name="Wiggle & Noise Modulators",
            description="Perlin and harmonic spatial noise modulators.",
            category=VideoStudioCategory.MOTION,
            implementation_state=ImplementationState.PLANNED,
            dependencies=[CapabilityDependency("video.motion.keyframes")],
            tags=["motion", "procedural"]
        ),

        # --- 3. TRACKING ---
        VideoStudioCapabilityDescriptor(
            id="video.tracking.point",
            name="Point Tracking",
            description="Single and dual-point pattern corner tracking.",
            category=VideoStudioCategory.TRACKING,
            implementation_state=ImplementationState.PLANNED,
            hardware_requirements=HardwareRequirements(requires_gpu=False),
            tags=["tracking", "point"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.tracking.feature",
            name="Feature Cloud Tracking",
            description="Multi-point feature cloud tracking (Lucas-Kanade/SIFT).",
            category=VideoStudioCategory.TRACKING,
            implementation_state=ImplementationState.PLANNED,
            hardware_requirements=HardwareRequirements(requires_gpu=True),
            tags=["tracking", "features"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.tracking.planar",
            name="Planar Surface Tracking",
            description="Homography 4-point surface tracking and screen replacement.",
            category=VideoStudioCategory.TRACKING,
            implementation_state=ImplementationState.PLANNED,
            hardware_requirements=HardwareRequirements(requires_gpu=True),
            tags=["tracking", "planar"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.tracking.face",
            name="Facial Landmark Tracking",
            description="Biometric 3D facial landmark mesh detection and tracking.",
            category=VideoStudioCategory.TRACKING,
            implementation_state=ImplementationState.PLANNED,
            ai_requirements=AIRequirements(abstract_capability="face_detection"),
            hardware_requirements=HardwareRequirements(requires_gpu=True),
            tags=["tracking", "face", "ai"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.tracking.subject",
            name="Subject Object Tracking",
            description="Bounding-box semantic object tracking and re-identification.",
            category=VideoStudioCategory.TRACKING,
            implementation_state=ImplementationState.PLANNED,
            ai_requirements=AIRequirements(abstract_capability="object_tracking"),
            tags=["tracking", "subject", "ai"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.tracking.license_plate",
            name="License Plate Redaction Tracking",
            description="Automated vehicle license plate tracking and redaction blur.",
            category=VideoStudioCategory.TRACKING,
            implementation_state=ImplementationState.PLANNED,
            ai_requirements=AIRequirements(abstract_capability="object_detection"),
            tags=["tracking", "security", "ai"]
        ),

        # --- 4. COMPOSITING / VFX ---
        VideoStudioCapabilityDescriptor(
            id="video.compositing.chroma_key",
            name="Chroma Key (Green/Blue Screen)",
            description="Color difference matte extraction and spill suppression.",
            category=VideoStudioCategory.COMPOSITING,
            implementation_state=ImplementationState.PLANNED,
            hardware_requirements=HardwareRequirements(requires_gpu=True),
            tags=["vfx", "keying"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.compositing.luma_key",
            name="Luma Keying",
            description="Luminance-thresholded transparency extraction.",
            category=VideoStudioCategory.COMPOSITING,
            implementation_state=ImplementationState.PLANNED,
            tags=["vfx", "keying"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.compositing.rotoscoping",
            name="Spline Rotoscoping",
            description="Vector spline manual and semi-automatic rotoscope masks.",
            category=VideoStudioCategory.COMPOSITING,
            implementation_state=ImplementationState.PLANNED,
            tags=["vfx", "masks"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.compositing.edge_matting",
            name="Edge Matting & Light Wrap",
            description="Despill filters and background edge light wrap integration.",
            category=VideoStudioCategory.COMPOSITING,
            implementation_state=ImplementationState.PLANNED,
            dependencies=[CapabilityDependency("video.compositing.chroma_key")],
            tags=["vfx", "matting"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.compositing.masks_feathering",
            name="Vector Masks & Feathering",
            description="Bezier shape masks with gaussian edge softness.",
            category=VideoStudioCategory.COMPOSITING,
            implementation_state=ImplementationState.PLANNED,
            tags=["vfx", "masks"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.compositing.blend_modes",
            name="Photometric Blend Modes",
            description="Photometric layer blend modes (Multiply, Screen, Overlay, etc.).",
            category=VideoStudioCategory.COMPOSITING,
            implementation_state=ImplementationState.PLANNED,
            tags=["vfx", "blends"]
        ),

        # --- 5. AI VIDEO ---
        VideoStudioCapabilityDescriptor(
            id="video.ai.optical_flow",
            name="AI Optical Flow Synthesis",
            description="Neural bidirectional motion vector field synthesis.",
            category=VideoStudioCategory.AI,
            implementation_state=ImplementationState.PLANNED,
            ai_requirements=AIRequirements(abstract_capability="optical_flow"),
            hardware_requirements=HardwareRequirements(requires_gpu=True, min_vram_mb=4096),
            tags=["ai", "motion"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.ai.scene_detection",
            name="Scene Cut Detection",
            description="Content-aware shot transition and edit point segmentation.",
            category=VideoStudioCategory.AI,
            implementation_state=ImplementationState.PLANNED,
            ai_requirements=AIRequirements(abstract_capability="scene_detection"),
            tags=["ai", "editing"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.ai.auto_reframe",
            name="Auto Reframe",
            description="Salient region detection for dynamic aspect ratio conversion (9:16 / 1:1).",
            category=VideoStudioCategory.AI,
            implementation_state=ImplementationState.PLANNED,
            ai_requirements=AIRequirements(abstract_capability="auto_reframe"),
            hardware_requirements=HardwareRequirements(requires_gpu=True),
            tags=["ai", "social"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.ai.depth_estimation",
            name="Monocular Depth Map Estimation",
            description="Neural relative depth map generation for 3D displacement.",
            category=VideoStudioCategory.AI,
            implementation_state=ImplementationState.PLANNED,
            ai_requirements=AIRequirements(abstract_capability="depth_estimation"),
            hardware_requirements=HardwareRequirements(requires_gpu=True, min_vram_mb=4096),
            tags=["ai", "depth", "vfx"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.ai.segmentation",
            name="AI Semantic Segmentation",
            description="Zero-shot subject isolation and alpha matte generation.",
            category=VideoStudioCategory.AI,
            implementation_state=ImplementationState.PLANNED,
            ai_requirements=AIRequirements(abstract_capability="segmentation"),
            hardware_requirements=HardwareRequirements(requires_gpu=True, min_vram_mb=4096),
            tags=["ai", "matte", "vfx"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.ai.morph_cut",
            name="Morph Cut AI Transition",
            description="Generative latent space interpolation cross-dissolve.",
            category=VideoStudioCategory.AI,
            implementation_state=ImplementationState.PLANNED,
            dependencies=[CapabilityDependency("video.ai.optical_flow")],
            tags=["ai", "transition"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.ai.generative_broll",
            name="Generative B-Roll Asset Synthesis",
            description="Latent diffusion and transformer b-roll generation.",
            category=VideoStudioCategory.AI,
            implementation_state=ImplementationState.PLANNED,
            ai_requirements=AIRequirements(abstract_capability="generative_video"),
            hardware_requirements=HardwareRequirements(requires_gpu=True, min_vram_mb=8192),
            tags=["ai", "generative"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.ai.transcription",
            name="Speech-to-Text Transcription",
            description="Timestamped word-level automated speech recognition.",
            category=VideoStudioCategory.AI,
            implementation_state=ImplementationState.PLANNED,
            ai_requirements=AIRequirements(abstract_capability="speech_to_text"),
            tags=["ai", "audio", "captions"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.ai.voice_isolation",
            name="AI Voice Isolation & Denoising",
            description="Deep neural noise suppression and speech isolation.",
            category=VideoStudioCategory.AI,
            implementation_state=ImplementationState.PLANNED,
            ai_requirements=AIRequirements(abstract_capability="voice_isolation"),
            tags=["ai", "audio"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.ai.voice_cloning",
            name="Voice Synthesis & Dubbing",
            description="Parametric neural voice cloning and automated multi-lingual dubbing.",
            category=VideoStudioCategory.AI,
            implementation_state=ImplementationState.PLANNED,
            ai_requirements=AIRequirements(abstract_capability="voice_synthesis"),
            tags=["ai", "audio", "dubbing"]
        ),

        # --- 6. AUDIO ---
        VideoStudioCapabilityDescriptor(
            id="video.audio.equalizer",
            name="Parametric EQ",
            description="Multi-band parametric equalizer with shelf and notch filters.",
            category=VideoStudioCategory.AUDIO,
            implementation_state=ImplementationState.PLANNED,
            tags=["audio", "eq"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.audio.deesser",
            name="De-Esser",
            description="Frequency-selective high-frequency sibilance attenuator.",
            category=VideoStudioCategory.AUDIO,
            implementation_state=ImplementationState.PLANNED,
            tags=["audio", "dynamics"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.audio.plosive_reduction",
            name="Plosive Reduction Filter",
            description="Sub-bass burst reduction filter.",
            category=VideoStudioCategory.AUDIO,
            implementation_state=ImplementationState.PLANNED,
            tags=["audio", "cleanup"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.audio.compressor",
            name="Dynamic Audio Compressor",
            description="Peak and RMS compressor with sidechain support.",
            category=VideoStudioCategory.AUDIO,
            implementation_state=ImplementationState.PLANNED,
            tags=["audio", "dynamics"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.audio.loudness_norm",
            name="Loudness Normalization",
            description="EBU R128 and ITU-R BS.1770 LUFS loudness matching.",
            category=VideoStudioCategory.AUDIO,
            implementation_state=ImplementationState.PLANNED,
            tags=["audio", "broadcast"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.audio.ducking",
            name="Auto Audio Ducking",
            description="Automated sidechain music attenuation during dialogue.",
            category=VideoStudioCategory.AUDIO,
            implementation_state=ImplementationState.PLANNED,
            dependencies=[CapabilityDependency("video.audio.compressor")],
            tags=["audio", "mix"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.audio.spatial_audio",
            name="Spatial & Surround Panning",
            description="Binaural 3D and 5.1/7.1 surround coordinate positioning.",
            category=VideoStudioCategory.AUDIO,
            implementation_state=ImplementationState.PLANNED,
            tags=["audio", "spatial"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.audio.reverb_echo",
            name="Convolution Reverb & Delay",
            description="Impulse response convolution reverb and feedback delay.",
            category=VideoStudioCategory.AUDIO,
            implementation_state=ImplementationState.PLANNED,
            tags=["audio", "fx"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.audio.pitch_correction",
            name="Pitch Correction & Shifting",
            description="Scale snapping and pitch transposition.",
            category=VideoStudioCategory.AUDIO,
            implementation_state=ImplementationState.PLANNED,
            tags=["audio", "pitch"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.audio.stem_separation",
            name="Stem Separation",
            description="Neural vocal, drums, bass, and accompaniment demixing.",
            category=VideoStudioCategory.AUDIO,
            implementation_state=ImplementationState.PLANNED,
            ai_requirements=AIRequirements(abstract_capability="stem_separation"),
            tags=["audio", "ai"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.audio.beat_detection",
            name="Beat & Transient Detection",
            description="Onset transient detection for rhythmic cut snapping.",
            category=VideoStudioCategory.AUDIO,
            implementation_state=ImplementationState.PLANNED,
            tags=["audio", "tempo"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.audio.routing",
            name="Sub-mix Routing & AUX Busses",
            description="Bus routing, AUX sends, and master processing chain.",
            category=VideoStudioCategory.AUDIO,
            implementation_state=ImplementationState.PLANNED,
            tags=["audio", "routing"]
        ),

        # --- 7. COLOR ---
        VideoStudioCapabilityDescriptor(
            id="video.color.lut",
            name="3D LUT Application",
            description=".cube and .3dl look-up table transform application.",
            category=VideoStudioCategory.COLOR,
            implementation_state=ImplementationState.PLANNED,
            tags=["color", "lut"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.color.wheels",
            name="3-Way Color Wheels",
            description="Lift, Gamma, Gain, and Offset balance controls.",
            category=VideoStudioCategory.COLOR,
            implementation_state=ImplementationState.PLANNED,
            tags=["color", "wheels"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.color.hsl",
            name="HSL Curve Adjustments",
            description="Hue vs Hue, Hue vs Sat, Lum vs Sat secondary curves.",
            category=VideoStudioCategory.COLOR,
            implementation_state=ImplementationState.PLANNED,
            tags=["color", "curves"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.color.scopes",
            name="Real-time Video Scopes",
            description="Waveform, Vectorscope, Histogram, and RGB Parade.",
            category=VideoStudioCategory.COLOR,
            implementation_state=ImplementationState.PLANNED,
            tags=["color", "scopes"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.color.shot_matching",
            name="Automated Shot Matching",
            description="Histogram transfer and neural reference color matching.",
            category=VideoStudioCategory.COLOR,
            implementation_state=ImplementationState.PLANNED,
            tags=["color", "ai"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.color.grain",
            name="Procedural Film Grain",
            description="Photographic emulsion grain simulation.",
            category=VideoStudioCategory.COLOR,
            implementation_state=ImplementationState.PLANNED,
            tags=["color", "film"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.color.halation",
            name="Halation & Bloom",
            description="Red-edge halation and optical glow simulation.",
            category=VideoStudioCategory.COLOR,
            implementation_state=ImplementationState.PLANNED,
            tags=["color", "film"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.color.vignette",
            name="Optical Vignette",
            description="Parametric radial lens light falloff shading.",
            category=VideoStudioCategory.COLOR,
            implementation_state=ImplementationState.PLANNED,
            tags=["color", "lens"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.color.hdr_rec2020",
            name="HDR & Rec.2020 Color Pipeline",
            description="Wide color gamut (Rec.2020, ACEScc) color management.",
            category=VideoStudioCategory.COLOR,
            implementation_state=ImplementationState.PLANNED,
            tags=["color", "hdr"]
        ),

        # --- 8. GRAPHICS & CAPTIONS ---
        VideoStudioCapabilityDescriptor(
            id="video.graphics.kinetic_typography",
            name="Kinetic Typography",
            description="Procedural animated text motion presets.",
            category=VideoStudioCategory.GRAPHICS,
            implementation_state=ImplementationState.PLANNED,
            tags=["graphics", "text"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.graphics.essential_graphics",
            name="Essential Graphics & Templates",
            description="Parametric template instantiation and typography.",
            category=VideoStudioCategory.GRAPHICS,
            implementation_state=ImplementationState.PLANNED,
            tags=["graphics", "templates"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.graphics.lower_thirds",
            name="Broadcast Lower Thirds",
            description="Broadcast title plates and graphic lower cards.",
            category=VideoStudioCategory.GRAPHICS,
            implementation_state=ImplementationState.PLANNED,
            tags=["graphics", "titles"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.graphics.callouts",
            name="Animated Graphic Callouts",
            description="Vector callout pointers, arrows, and highlight bounding boxes.",
            category=VideoStudioCategory.GRAPHICS,
            implementation_state=ImplementationState.PLANNED,
            tags=["graphics", "callouts"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.graphics.data_viz",
            name="Animated Data Visualizations",
            description="Dynamic keyframed bar, line, and pie chart data animations.",
            category=VideoStudioCategory.GRAPHICS,
            implementation_state=ImplementationState.PLANNED,
            tags=["graphics", "data"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.graphics.thumbnails",
            name="Thumbnail Generation",
            description="High-resolution poster frame capture and title rendering.",
            category=VideoStudioCategory.GRAPHICS,
            implementation_state=ImplementationState.PLANNED,
            tags=["graphics", "thumbnails"]
        ),

        # --- 9. MEDIA & RECORDING ---
        VideoStudioCapabilityDescriptor(
            id="video.media.proxy_creation",
            name="Proxy Video Generation",
            description="Background low-resolution editing proxy transcoding.",
            category=VideoStudioCategory.MEDIA,
            implementation_state=ImplementationState.PLANNED,
            tags=["media", "proxies"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.media.watch_folder",
            name="Watch Folder Auto-Ingest",
            description="Filesystem folder monitoring for automated asset ingest.",
            category=VideoStudioCategory.MEDIA,
            implementation_state=ImplementationState.PLANNED,
            tags=["media", "ingest"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.media.metadata",
            name="Container & Codec Metadata Parser",
            description="Exif, container, frame rate, and color space header parser.",
            category=VideoStudioCategory.MEDIA,
            implementation_state=ImplementationState.PLANNED,
            tags=["media", "metadata"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.media.consolidation",
            name="Media Consolidation & Pruning",
            description="Project collection and used-clip archive extraction.",
            category=VideoStudioCategory.MEDIA,
            implementation_state=ImplementationState.PLANNED,
            tags=["media", "archive"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.media.archive",
            name="Lossless Project Archiving",
            description="Cold storage packaging with SHA-256 asset manifests.",
            category=VideoStudioCategory.MEDIA,
            implementation_state=ImplementationState.PLANNED,
            tags=["media", "archive"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.recording.screen",
            name="Screen Recording Engine",
            description="Hardware-accelerated desktop canvas recording.",
            category=VideoStudioCategory.RECORDING,
            implementation_state=ImplementationState.PLANNED,
            hardware_requirements=HardwareRequirements(requires_hw_encoder=True),
            tags=["recording", "screen"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.recording.webcam",
            name="Webcam Video Capture",
            description="USB/UVC video input capture with chroma key preview.",
            category=VideoStudioCategory.RECORDING,
            implementation_state=ImplementationState.PLANNED,
            tags=["recording", "camera"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.recording.system_audio",
            name="Loopback System Audio Capture",
            description="Internal loopback workstation audio recording.",
            category=VideoStudioCategory.RECORDING,
            implementation_state=ImplementationState.PLANNED,
            tags=["recording", "audio"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.recording.cursor_smoothing",
            name="Cursor Trajectory Smoothing",
            description="High-frequency mouse trajectory filtering and cinematic zoom.",
            category=VideoStudioCategory.RECORDING,
            implementation_state=ImplementationState.PLANNED,
            tags=["recording", "cursor"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.recording.auto_zoom",
            name="Automatic Focus Hotspot Zoom",
            description="Automatic framing and zoom into user click focus points.",
            category=VideoStudioCategory.RECORDING,
            implementation_state=ImplementationState.PLANNED,
            tags=["recording", "zoom"]
        ),

        # --- 10. RENDERING & EXPORT ---
        VideoStudioCapabilityDescriptor(
            id="video.export.background_render",
            name="Background Timeline Rendering",
            description="Asynchronous out-of-process frame rendering queue.",
            category=VideoStudioCategory.RENDERING,
            implementation_state=ImplementationState.PLANNED,
            tags=["export", "render"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.export.batch",
            name="Batch Export Queue",
            description="Multi-resolution, multi-preset parallel encoding queue.",
            category=VideoStudioCategory.EXPORT,
            implementation_state=ImplementationState.PLANNED,
            tags=["export", "batch"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.export.social",
            name="Social Publishing Presets",
            description="Vertical 9:16 and platform-specific profile targets.",
            category=VideoStudioCategory.EXPORT,
            implementation_state=ImplementationState.PLANNED,
            tags=["export", "social"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.export.alpha",
            name="Alpha Channel Transparent Export",
            description="ProRes 4444 and VP9 transparent alpha delivery.",
            category=VideoStudioCategory.EXPORT,
            implementation_state=ImplementationState.PLANNED,
            tags=["export", "alpha"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.export.timecode_burnin",
            name="SMPTE Timecode Burn-In",
            description="Visual frame-accurate timecode burn-in overlay.",
            category=VideoStudioCategory.EXPORT,
            implementation_state=ImplementationState.PLANNED,
            tags=["export", "burnin"]
        ),

        # --- 11. COLLABORATION ---
        VideoStudioCapabilityDescriptor(
            id="video.collab.comments",
            name="Frame-Accurate Review Comments",
            description="SMPTE timestamp-linked commentary and freehand drawings.",
            category=VideoStudioCategory.COLLABORATION,
            implementation_state=ImplementationState.PLANNED,
            tags=["collab", "comments"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.collab.review",
            name="Client Review Portal",
            description="Client web playback portal with approval workflows.",
            category=VideoStudioCategory.COLLABORATION,
            implementation_state=ImplementationState.PLANNED,
            tags=["collab", "review"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.collab.approval_states",
            name="OMNIA Approval Gateway Sync",
            description="Pass/Reject/Revision states integrated with OMNIA approval gateway.",
            category=VideoStudioCategory.COLLABORATION,
            implementation_state=ImplementationState.PLANNED,
            tags=["collab", "approval"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.collab.version_history",
            name="Project Snapshot Version History",
            description="Immutable timeline branch snapshots and rollback points.",
            category=VideoStudioCategory.COLLABORATION,
            implementation_state=ImplementationState.PLANNED,
            tags=["collab", "versioning"]
        ),

        # --- 12. EXTENSIONS ---
        VideoStudioCapabilityDescriptor(
            id="video.extensions.python_api",
            name="Python Automation Scripting API",
            description="Headless script manipulation of timelines and clips.",
            category=VideoStudioCategory.EXTENSIONS,
            implementation_state=ImplementationState.PLANNED,
            tags=["extensions", "python"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.extensions.control_surfaces",
            name="External Control Surfaces Integration",
            description="Jog/shuttle wheels, Loupedeck, and Stream Deck hardware hooks.",
            category=VideoStudioCategory.EXTENSIONS,
            implementation_state=ImplementationState.PLANNED,
            tags=["extensions", "hardware"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.extensions.midi",
            name="MIDI Control Protocol",
            description="Fader and knob mapping to audio and color controls.",
            category=VideoStudioCategory.EXTENSIONS,
            implementation_state=ImplementationState.PLANNED,
            tags=["extensions", "midi"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.extensions.editing_consoles",
            name="Dedicated Editing Consoles",
            description="Dedicated console hardware protocol translation.",
            category=VideoStudioCategory.EXTENSIONS,
            implementation_state=ImplementationState.PLANNED,
            tags=["extensions", "consoles"]
        ),
        # --- 13. MOTION TRACKING & CAMERA STABILIZATION ---
        VideoStudioCapabilityDescriptor(
            id="video.tracking.point",
            name="Point Optical Flow Tracking",
            description="Lucas-Kanade optical flow feature tracking with forward-backward error validation.",
            category=VideoStudioCategory.TRACKING,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["tracking", "point", "optical_flow"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.tracking.region",
            name="Region Template Matching Tracking",
            description="Normalized cross-correlation template matching object tracker.",
            category=VideoStudioCategory.TRACKING,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["tracking", "region", "template_match"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.tracking.effects_binding",
            name="Track to Effects & Transform Binding",
            description="Automated binding of tracking motion data to animatable keyframes, effects, and masks.",
            category=VideoStudioCategory.TRACKING,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["tracking", "keyframes", "animation"]
        ),
        # --- 14. CHROMA KEYING & MATTE EXTRACTION ---
        VideoStudioCapabilityDescriptor(
            id="video.compositing.chroma_key",
            name="Production Chroma Keying Engine",
            description="Color-space-aware green/blue screen extraction.",
            category=VideoStudioCategory.COMPOSITING,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["chroma_key", "green_screen", "compositing"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.compositing.matte_extraction",
            name="Alpha Matte Generation & Refinement",
            description="Edge feathering, choke, expansion, and morphological cleanup.",
            category=VideoStudioCategory.COMPOSITING,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["matte", "alpha", "feather"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.compositing.spill_suppression",
            name="Chroma Spill Suppression",
            description="Edge spill neutralization and desaturation.",
            category=VideoStudioCategory.COMPOSITING,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["spill", "suppression", "color"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.compositing.key_sampling",
            name="Interactive Key Color Sampling",
            description="Frame color sampling and multi-point keying.",
            category=VideoStudioCategory.COMPOSITING,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["sampling", "color", "picker"]
        ),
        # --- 15. DENOISING & RESTORATION ---
        VideoStudioCapabilityDescriptor(
            id="video.restoration.spatial_denoise",
            name="Edge-Preserving Spatial Denoising",
            description="Bilateral, Non-Local Means, and Guided spatial noise reduction.",
            category=VideoStudioCategory.MOTION,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["denoise", "spatial", "bilateral"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.restoration.temporal_denoise",
            name="Motion-Safe Temporal Denoising",
            description="Adaptive multi-frame accumulation with ghosting prevention.",
            category=VideoStudioCategory.MOTION,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["denoise", "temporal", "accumulation"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.restoration.artifact_removal",
            name="Sensor Defect & Deblocking Restoration",
            description="Dead pixel detection, compression deblocking, and unsharp masking.",
            category=VideoStudioCategory.MOTION,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["restoration", "dead_pixel", "deblocking"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.restoration.luma_chroma_separation",
            name="Independent Luma & Chroma Filtering",
            description="Targeted luminance grain and chrominance noise suppression.",
            category=VideoStudioCategory.MOTION,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["denoise", "luma", "chroma"]
        ),
        # --- 16. UPSCALING & SUPER-RESOLUTION ---
        VideoStudioCapabilityDescriptor(
            id="video.rendering.spatial_upscale",
            name="Conventional High-Fidelity Resampling",
            description="Lanczos4, Bicubic, Bilinear, and Nearest-Neighbor interpolation.",
            category=VideoStudioCategory.RENDERING,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["upscale", "spatial", "lanczos"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.rendering.detail_enhancement",
            name="Edge Detail Enhancement & Sharpening",
            description="Unsharp masking with halo overshoot suppression.",
            category=VideoStudioCategory.RENDERING,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["sharpen", "enhancement", "detail"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.rendering.denoise_integration",
            name="Pre-Upscale Denoise Pipeline Integration",
            description="Module 25 noise removal prior to resolution magnification.",
            category=VideoStudioCategory.RENDERING,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["upscale", "denoise", "integration"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.rendering.learned_super_res",
            name="Learned Super-Resolution Model Runtime",
            description="Model-backed deep learning super-resolution adapter.",
            category=VideoStudioCategory.RENDERING,
            implementation_state=ImplementationState.EXPERIMENTAL,
            tags=["super_resolution", "ai", "model"]
        ),
        # --- 17. FRAME INTERPOLATION & FRAME-RATE CONVERSION ---
        VideoStudioCapabilityDescriptor(
            id="video.interpolation.frame_duplication",
            name="Deterministic Frame Duplication",
            description="Nearest-neighbor temporal frame rate conversion.",
            category=VideoStudioCategory.TIMELINE,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["interpolation", "fps", "duplication"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.interpolation.frame_blending",
            name="Timestamp-Weighted Frame Blending",
            description="Linear crossfade intermediate frame blending.",
            category=VideoStudioCategory.TIMELINE,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["interpolation", "fps", "blend"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.interpolation.motion_compensated",
            name="Dense Optical Flow Motion Compensation",
            description="Farneback bi-directional motion-warped frame synthesis.",
            category=VideoStudioCategory.TIMELINE,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["interpolation", "optical_flow", "motion"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.interpolation.scene_cut_detection",
            name="Motion-Safe Scene Cut Protection",
            description="Mean Absolute Difference cut detection and morphing prevention.",
            category=VideoStudioCategory.TIMELINE,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["scene_cut", "protection", "cut"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.interpolation.learned_model",
            name="Learned Neural Frame Interpolation",
            description="RIFE / deep learning model interpolation adapter.",
            category=VideoStudioCategory.TIMELINE,
            implementation_state=ImplementationState.EXPERIMENTAL,
            tags=["interpolation", "ai", "rife"]
        ),
        # --- 18. DEBLURRING & MOTION BLUR PROCESSING ---
        VideoStudioCapabilityDescriptor(
            id="video.effects.deblur_wiener",
            name="Wiener Deconvolution Restoration",
            description="Frequency-domain deblurring with Gibbs ringing suppression.",
            category=VideoStudioCategory.MOTION,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["deblur", "wiener", "restoration"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.effects.motion_blur_generation",
            name="Camera Shutter Motion Blur Generation",
            description="Shutter-angle simulation and directional motion trails.",
            category=VideoStudioCategory.MOTION,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["motion_blur", "shutter", "generation"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.effects.motion_blur_reduction",
            name="Velocity-Aware Motion Blur Reduction",
            description="Directional deconvolution guided by tracking vectors.",
            category=VideoStudioCategory.MOTION,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["motion_blur", "reduction", "deconvolution"]
        ),
        # --- 19. LIGHTING, EXPOSURE & RELIGHTING ---
        VideoStudioCapabilityDescriptor(
            id="video.lighting.global_exposure",
            name="Deterministic Video Exposure & Tonal Engine",
            description="Deterministic photographic exposure compensation (stops), highlights/shadows, and midtone gamma.",
            category=VideoStudioCategory.COLOR,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["lighting", "exposure", "color", "tonal"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.lighting.localized_regions",
            name="Parametric Localized Lighting & Relighting Regions",
            description="Radial, directional, and polygon mask lighting regions with falloff feathering and blend equations.",
            category=VideoStudioCategory.COLOR,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["lighting", "relighting", "masks", "blending"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.lighting.scene_aware_relighting",
            name="Scene-Aware AI Relighting Extension",
            description="Scene-aware normal/depth relighting extension interface. Inactive until physical model is loaded.",
            category=VideoStudioCategory.AI,
            implementation_state=ImplementationState.EXPERIMENTAL,
            tags=["lighting", "ai", "relighting", "experimental"]
        ),
        # --- 20. LENS DISTORTION & OPTICAL CORRECTION ---
        VideoStudioCapabilityDescriptor(
            id="video.lens.distortion_correction",
            name="Geometric Lens Distortion Correction",
            description="Brown-Conrady radial (k1, k2, k3) and tangential (p1, p2) optical correction with subpixel inverse remapping.",
            category=VideoStudioCategory.EDITING,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["lens", "distortion", "optics", "geometry"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.lens.profile_matching",
            name="Optical Lens Profile Library & Matching",
            description="Manufacturer calibration profile matching and automatic parameter transfer.",
            category=VideoStudioCategory.MEDIA,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["lens", "profiles", "calibration", "metadata"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.lens.chromatic_aberration",
            name="Lateral Chromatic Aberration Correction",
            description="Channel-aware radial displacement correction for red/blue optical fringing.",
            category=VideoStudioCategory.COLOR,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["lens", "chromatic_aberration", "color", "fringing"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.lens.vignetting_correction",
            name="Optical Vignetting & Corner Light Falloff Correction",
            description="Smooth radial gain compensation for optical lens corner darkening.",
            category=VideoStudioCategory.COLOR,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["lens", "vignetting", "falloff", "exposure"]
        ),
        # --- 21. FILM GRAIN, VIDEO TEXTURE & ANALOG EMULATION ---
        VideoStudioCapabilityDescriptor(
            id="video.texture.film_grain",
            name="Deterministic Procedural Film Grain Synthesis",
            description="Seeded procedural normal and coarse film grain with Luma/Chroma split and tonal curve weighting.",
            category=VideoStudioCategory.MOTION,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["grain", "film", "texture", "noise"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.texture.analog_emulation",
            name="Analog Film Emulation & Texture Artifacts",
            description="Subpixel gate weave jitter, anti-halation layer highlight glow bloom, and procedural wear.",
            category=VideoStudioCategory.MOTION,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["analog", "halation", "gate_weave", "wear"]
        ),
        # --- 22. DEPTH ESTIMATION, DEPTH MAPS & 2.5D COMPOSITING (MODULE 32) ---
        VideoStudioCapabilityDescriptor(
            id="video.depth.map_processing",
            name="Depth Map Import & Range Processing",
            description="Import, normalize, invert, and slice 2D floating-point and grayscale depth maps.",
            category=VideoStudioCategory.COMPOSITING,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["depth", "range", "matte", "compositing"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.depth.compositing_25d",
            name="2.5D Parallax & Depth-of-Field Compositing",
            description="Depth-driven camera parallax coordinate warping, optical defocus blur, and occlusion.",
            category=VideoStudioCategory.COMPOSITING,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["depth", "parallax", "dof", "2.5d"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.depth.estimation_ai",
            name="Monocular AI Depth Estimation",
            description="Monocular neural depth estimation interface (requires loaded weights runtime).",
            category=VideoStudioCategory.AI,
            implementation_state=ImplementationState.EXPERIMENTAL,
            tags=["depth", "ai", "monocular", "neural"]
        ),
        # --- 23. OPTICAL FLOW, MOTION VECTORS & MOTION-AWARE PROCESSING (MODULE 33) ---
        VideoStudioCapabilityDescriptor(
            id="video.motion.dense_optical_flow",
            name="Dense Optical Flow Estimation",
            description="Pixel-dense Gunnar Farneback and DIS optical flow with forward-backward consistency verification.",
            category=VideoStudioCategory.MOTION,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["motion", "optical_flow", "dense", "vectors"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.motion.sparse_feature_flow",
            name="Sparse Feature Optical Flow Tracking",
            description="Pyramidal Lucas-Kanade sparse motion tracking with Shi-Tomasi feature selection.",
            category=VideoStudioCategory.MOTION,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["motion", "tracking", "sparse", "lucas_kanade"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.motion.ai_neural_flow",
            name="Deep Neural Optical Flow (RAFT / FlowNet)",
            description="Deep learning neural motion estimation adapter interface (requires loaded model runtime).",
            category=VideoStudioCategory.AI,
            implementation_state=ImplementationState.EXPERIMENTAL,
            tags=["motion", "ai", "raft", "neural"]
        ),
        # --- 24. OBJECT SEGMENTATION, SEMANTIC MASKING & SUBJECT ISOLATION (MODULE 34) ---
        VideoStudioCapabilityDescriptor(
            id="video.segmentation.mask_refinement",
            name="Semantic Mask Refinement & Edge Matting",
            description="Morphological erosion, dilation, edge-aware bilateral feathering, hole filling, and multi-matte boolean combinations.",
            category=VideoStudioCategory.COMPOSITING,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["segmentation", "mask", "refinement", "feathering"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.segmentation.temporal_propagation",
            name="Optical-Flow-Assisted Mask Propagation",
            description="Inter-frame mask propagation powered by Module 33 dense optical flow with scene-cut reset protection.",
            category=VideoStudioCategory.COMPOSITING,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["segmentation", "propagation", "optical_flow", "temporal"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.segmentation.ai_inference",
            name="AI Subject & Object Segmentation",
            description="Interactive point and box promptable neural segmentation runtime (requires downloaded model weights).",
            category=VideoStudioCategory.AI,
            implementation_state=ImplementationState.EXPERIMENTAL,
            tags=["segmentation", "ai", "sam", "promptable"]
        ),
        # --- 25. VIDEO UNDERSTANDING, SCENE ANALYSIS & CONTENT INTELLIGENCE (MODULE 35) ---
        VideoStudioCapabilityDescriptor(
            id="video.intelligence.scene_detection",
            name="Shot Boundary & Scene Detection",
            description="Multi-metric shot boundary detection (HSV histogram correlation, MAD, Sobel edge difference, fade-in/out).",
            category=VideoStudioCategory.EDITING,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["intelligence", "scene", "shot_detection", "transitions"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.intelligence.visual_classification",
            name="Visual Content & Composition Classification",
            description="Deterministic lighting, camera motion kinematics, and composition framing scale classification.",
            category=VideoStudioCategory.AI,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["intelligence", "visual", "composition", "lighting"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.intelligence.semantic_search",
            name="Media Intelligence & Semantic Search",
            description="Search across shot classifications, visual tags, scene summaries, and speech transcripts with direct timestamp targets.",
            category=VideoStudioCategory.MEDIA,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["intelligence", "search", "semantic", "transcripts"]
        ),
        # --- 26. AI-ASSISTED EDITING, AUTOMATED ROUGH CUT & EDIT DECISION ENGINE (MODULE 36) ---
        VideoStudioCapabilityDescriptor(
            id="video.editing.rough_cut_decision_engine",
            name="AI Rough Cut & Edit Decision Engine",
            description="Synthesizes visual intelligence and briefs into editable, non-destructive rough cuts.",
            category=VideoStudioCategory.EDITING,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["editing", "rough_cut", "edl", "assembly"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.editing.pacing_strategy",
            name="Pacing & Narrative Assembly",
            description="Rhythmic shot duration mapping and narrative structuring for automated assembly.",
            category=VideoStudioCategory.EDITING,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["editing", "pacing", "narrative", "rhythm"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.editing.ai_assisted_assembly",
            name="AI-Assisted Timeline Assembly",
            description="Interactive human-in-the-loop rough cut generation with timeline transaction commit.",
            category=VideoStudioCategory.AI,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["editing", "ai", "assembly", "transaction"]
        ),
        # --- 27. QUALITY CONTROL, TECHNICAL VALIDATION & COMPLIANCE (MODULE 37) ---
        VideoStudioCapabilityDescriptor(
            id="video.qc.technical_validation",
            name="Video Technical QC & Validation",
            description="Deterministic technical inspection of resolution, black frames, freeze frames, and VFR.",
            category=VideoStudioCategory.MEDIA,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["qc", "validation", "video", "frames"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.qc.audio_compliance",
            name="Audio Compliance & Metering QC",
            description="Peak amplitude, clipping, silence gap, and channel layout validation.",
            category=VideoStudioCategory.AUDIO,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["qc", "audio", "clipping", "metering"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.qc.delivery_profiles",
            name="Delivery Profiles & Compliance Engine",
            description="Configurable delivery compliance profiles for web, broadcast, and social distribution.",
            category=VideoStudioCategory.EXPORT,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["qc", "delivery", "compliance", "profiles"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.qc.timeline_integrity",
            name="Timeline Sequence Integrity QC",
            description="Structural checks for timeline gaps, unlinked clips, and missing media.",
            category=VideoStudioCategory.TIMELINE,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["qc", "timeline", "integrity", "gaps"]
        ),
        # --- 28. PROJECT PACKAGING, MEDIA ARCHIVING & PORTABLE WORKFLOW (MODULE 38) ---
        VideoStudioCapabilityDescriptor(
            id="video.packaging.portable_archive",
            name="Portable Project Packaging & Archiving",
            description="Bundles project documents, original media, audio, and graphics into a verified standalone package.",
            category=VideoStudioCategory.COLLABORATION,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["packaging", "archive", "export", "portable"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.packaging.integrity_verification",
            name="Cryptographic Package Verification",
            description="SHA-256 manifest-to-content validation, truncation detection, and zip bomb defense.",
            category=VideoStudioCategory.MEDIA,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["integrity", "checksum", "verification", "security"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.packaging.safe_restoration",
            name="Safe Project Restoration & Relinking",
            description="Path traversal-safe archive extraction and automated local asset relinking.",
            category=VideoStudioCategory.COLLABORATION,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["restoration", "relinking", "unzip", "import"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.packaging.project_snapshots",
            name="Project Snapshot Lifecycle Management",
            description="Creates and tracks named historical revision checkpoints with checksums.",
            category=VideoStudioCategory.MEDIA,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["snapshots", "revisions", "versioning"]
        ),
        # --- 29. WORKFLOW AUTOMATION, BATCH OPERATIONS & MACROS (MODULE 39) ---
        VideoStudioCapabilityDescriptor(
            id="video.workflow.automation_engine",
            name="Workflow Automation & Macro Engine",
            description="Composable DAG workflow execution across Video Studio services with cycle detection.",
            category=VideoStudioCategory.EDITING,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["workflow", "automation", "macros", "dag"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.workflow.batch_operations",
            name="Batch Operations & Processing",
            description="Concurrent multi-target processing with item failure isolation and aggregate progress.",
            category=VideoStudioCategory.MEDIA,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["batch", "concurrency", "multi_target"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.workflow.safety_gates",
            name="Human Approval & Safety Gates",
            description="Non-destructive approval gates and restricted conditional branching before execution.",
            category=VideoStudioCategory.EDITING,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["safety", "approval", "gates", "review"]
        ),
        # --- 30. COLLABORATION, REVIEW & ANNOTATION (MODULE 40) ---
        VideoStudioCapabilityDescriptor(
            id="video.collaboration.review_sessions",
            name="Project & Sequence Review Sessions",
            description="Version-aware multi-user review sessions with role-based access control.",
            category=VideoStudioCategory.COLLABORATION,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["collaboration", "review", "rbac"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.collaboration.timestamped_annotations",
            name="Timestamped & Spatial Video Annotations",
            description="Point, range, and normalized rectangular bounding-box visual annotations.",
            category=VideoStudioCategory.COLLABORATION,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["collaboration", "annotations", "spatial"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.collaboration.version_aware_review",
            name="Version-Aware Review & Stale Comment Detection",
            description="Automatic drift tracking between comments and subsequent timeline edits.",
            category=VideoStudioCategory.COLLABORATION,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["collaboration", "revisions", "stale_detection"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.collaboration.decision_audit",
            name="Formal Review Decisions & Audit Trail",
            description="Non-destructive approval workflows with immutable decision audit logging.",
            category=VideoStudioCategory.COLLABORATION,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["collaboration", "decisions", "approvals", "audit"]
        ),
        # --- 31. VERSION CONTROL, BRANCHING & RECOVERY (MODULE 41) ---
        VideoStudioCapabilityDescriptor(
            id="video.versioning.revision_snapshots",
            name="Project Revision Snapshots & Checkpoints",
            description="Immutable, content-addressed project timeline snapshot capture with integrity hashing.",
            category=VideoStudioCategory.TIMELINE,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["versioning", "snapshots", "history", "checkpoints"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.versioning.timeline_branching",
            name="Timeline Branching & Experimental Edits",
            description="Lightweight timeline branching, safe branch switching, and divergence tracking.",
            category=VideoStudioCategory.TIMELINE,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["versioning", "branching", "experiments"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.versioning.structural_comparison",
            name="Visual & Structural Revision Diff Engine",
            description="Fine-grained structural difference reporting across tracks, clips, settings, and duration.",
            category=VideoStudioCategory.TIMELINE,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["versioning", "diff", "comparison"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.versioning.non_destructive_recovery",
            name="Non-Destructive Project Recovery & Restore",
            description="Safe timeline restore with pre-flight media validation and atomic pre-restore checkpoints.",
            category=VideoStudioCategory.TIMELINE,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["versioning", "recovery", "restore", "safety"]
        ),
        # --- 32. MEDIA PROVENANCE, DEPENDENCY GRAPH & RELINKING (MODULE 42) ---
        VideoStudioCapabilityDescriptor(
            id="video.provenance.asset_tracking",
            name="Media Asset Provenance & History Tracking",
            description="Immutable audit trail of asset origins, moves, content fingerprints, and relink history.",
            category=VideoStudioCategory.MEDIA,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["provenance", "audit", "fingerprint", "assets"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.provenance.dependency_graph",
            name="Project Resource Dependency Graph",
            description="Directed acyclic graph tracking dependencies between projects, sequences, clips, and media.",
            category=VideoStudioCategory.MEDIA,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["dependencies", "dag", "graph", "relationships"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.provenance.intelligent_relinking",
            name="Intelligent Multi-Tier Asset Relinking Engine",
            description="Safe media relinking with multi-tier candidate scoring, checksum verification, and rollback.",
            category=VideoStudioCategory.MEDIA,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["relinking", "recovery", "matching", "offline_media"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.provenance.usage_and_cleanup_safety",
            name="Asset Usage Analysis & Deletion Safety Guard",
            description="Pre-deletion dependency verification across active timelines, revisions, and project branches.",
            category=VideoStudioCategory.MEDIA,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["cleanup", "safety", "deletion_guard", "unused_assets"]
        ),
        # --- 33. MEDIA CONFORM, OFFLINE EDITING & RELINK (MODULE 43) ---
        VideoStudioCapabilityDescriptor(
            id="video.conform.offline_proxy_workflow",
            name="Offline Proxy Editing & Source Binding",
            description="Preserves frame-accurate identity and timecode mapping between proxies and original media.",
            category=VideoStudioCategory.MEDIA,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["conform", "proxy", "offline", "workflow"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.conform.representation_switching",
            name="Seamless Media Representation Switching",
            description="Non-destructive instant toggle between proxy and original sources during timeline playback.",
            category=VideoStudioCategory.TIMELINE,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["playback", "proxy_switching", "representation"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.conform.online_relink_engine",
            name="High-Resolution Online Conform Engine",
            description="Preflight audit and transactional conform swapping from proxies back to original media.",
            category=VideoStudioCategory.MEDIA,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["conform", "online_relink", "master_render"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.conform.render_validation_gate",
            name="Final Quality Render Conform Validation Gate",
            description="Enforces strict pre-render check preventing proxy media from leaking into master exports.",
            category=VideoStudioCategory.EXPORT,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["export", "validation", "master_render", "safety_gate"]
        ),
        # --- 34. RENDER PIPELINE ORCHESTRATION & FAULT RECOVERY (MODULE 44) ---
        VideoStudioCapabilityDescriptor(
            id="video.render.orchestration_lifecycle",
            name="Render Pipeline Lifecycle Orchestration",
            description="State-machine governed render lifecycle (Queued, Preparing, Rendering, Verifying, Completed).",
            category=VideoStudioCategory.RENDERING,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["render", "orchestration", "lifecycle", "queue"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.render.worker_scheduling",
            name="Worker Dispatch & Concurrency Control",
            description="Worker capability matching, priority queueing, and bounded concurrent resource scheduling.",
            category=VideoStudioCategory.RENDERING,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["workers", "scheduling", "concurrency", "dispatch"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.render.fault_recovery_and_retry",
            name="Transient Fault Recovery & Safe Retry",
            description="Automatic transient failure classification, interruption recovery, and clean temp cleanup.",
            category=VideoStudioCategory.RENDERING,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["recovery", "fault_tolerance", "retry", "cleanup"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.render.output_verification_and_publish",
            name="Output Artifact Verification & Atomic Publish",
            description="Post-render verification of headers, duration, and content hashes before atomic publication.",
            category=VideoStudioCategory.EXPORT,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["export", "verification", "atomic_publish", "sha256"]
        ),
        # --- 35. REMOTE WORKER PROTOCOL & DISTRIBUTED RENDERING (MODULE 45) ---
        VideoStudioCapabilityDescriptor(
            id="video.render.remote_worker_protocol",
            name="Remote Render Worker Protocol & Verification",
            description="Secure versioned protocol for remote worker registration, heartbeat tracking, and job dispatch.",
            category=VideoStudioCategory.RENDERING,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["remote", "render_farm", "protocol", "distributed"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.render.distributed_job_dispatch",
            name="Distributed Job Dispatch & Fencing Leases",
            description="Secure job assignment with monotonic fencing tokens and scoped asset transfer boundaries.",
            category=VideoStudioCategory.RENDERING,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["dispatch", "fencing_token", "leases", "security"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.render.worker_fault_recovery",
            name="Worker Disconnection Detection & Auto-Recovery",
            description="Heartbeat timeout tracking, zombie task recovery, and automatic job reassignment.",
            category=VideoStudioCategory.RENDERING,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["fault_tolerance", "recovery", "heartbeat", "zombie_cleanup"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.render.chunked_artifact_transfer",
            name="Chunked Media Transfer & Ingest Verification",
            description="Streaming chunked media artifact transfer with SHA-256 verification and atomic ingest.",
            category=VideoStudioCategory.EXPORT,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["transfer", "chunking", "artifact", "integrity"]
        ),
        # --- 36. RENDER FARM MONITORING, COST ATTRIBUTION & CAPACITY PLANNING (MODULE 46) ---
        VideoStudioCapabilityDescriptor(
            id="video.render.telemetry_collection",
            name="Structured Render Job Telemetry Collection",
            description="End-to-end stage duration, frame throughput, resource metrics, and artifact verification profiling.",
            category=VideoStudioCategory.RENDERING,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["telemetry", "profiling", "timing", "frames"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.render.worker_fleet_monitoring",
            name="Render Farm Worker Fleet Monitoring",
            description="Live worker availability, heartbeat delay, job concurrency saturation, and hardware metrics.",
            category=VideoStudioCategory.RENDERING,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["monitoring", "workers", "fleet", "health"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.render.cost_attribution_engine",
            name="Render Compute Cost Attribution Engine",
            description="Transparent compute, worker time, storage, and transfer cost attribution based on measured metrics.",
            category=VideoStudioCategory.EXPORT,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["cost", "attribution", "pricing", "billing"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.render.capacity_planning_analytics",
            name="Render Capacity Planning & Predictive Analytics",
            description="Statistical queue pressure, bottleneck identification, and worker saturation forecasting.",
            category=VideoStudioCategory.RENDERING,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["capacity", "planning", "analytics", "forecasting"]
        ),
        VideoStudioCapabilityDescriptor(
            id="video.render.operational_alerting",
            name="Operational Incident Alerting & Deduplication",
            description="Real-time alert evaluation for worker timeouts, queue backlogs, and repeated verification failures.",
            category=VideoStudioCategory.RENDERING,
            implementation_state=ImplementationState.IMPLEMENTED,
            tags=["alerting", "incidents", "deduplication", "health"]
        ),
    ]

    for cap in capabilities_data:
        if registry.get(cap.id) is not None:
            count += 1
            continue
        ok, _ = registry.register(cap, auth_token="core")
        if ok:
            count += 1

    return count
