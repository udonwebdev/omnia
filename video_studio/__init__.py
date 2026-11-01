"""OMNIA Video Studio — Module 0: Architecture, Isolation & Integration Foundation.

This package provides the complete, isolated architectural foundation for the optional
OMNIA Video Studio subsystem.
"""

from video_studio.models import (
    VideoStudioState,
    VideoStudioMetadata,
    VideoStudioFeatureContract,
    VideoStudioCapabilities,
    ComputeBackend,
    ComputeCapabilities,
    VideoStudioError,
    MediaError,
    CodecError,
    DecodeError,
    EncodeError,
    RenderError,
    GPUError,
    AIProcessingError,
    StorageError,
    ExportError,
)
from video_studio.service import (
    VideoStudioService,
    video_studio_service,
)
from video_studio.catalog import VIDEO_STUDIO_CAPABILITY_CATALOG
from video_studio.registry_models import (
    VideoStudioCategory,
    VideoStudioCapabilityStatus,
    ImplementationState,
    HardwareRequirements,
    PlatformRequirements,
    AIRequirements,
    CapabilityDependency,
    CapabilityProviderDescriptor,
    CapabilityHealthReport,
    VideoStudioCapabilityDescriptor,
    AccelerationAPI,
)
from video_studio.registry import (
    VideoStudioCapabilityRegistry,
    video_studio_capability_registry,
)
from video_studio.hardware import VideoStudioHardwareDetector
from video_studio.catalog_loader import populate_roadmap_capabilities

# Module 2 Exports
from video_studio.media_models import (
    AssetMediaType,
    AssetLifecycleStatus,
    ContainerFormat,
    VideoCodec,
    AudioCodec,
    FrameRateMode,
    MediaRelationshipType,
    ProxyStatus,
    RationalTime,
    SMPTETimecode,
    AudioStreamInfo,
    VideoStreamInfo,
    ProxyDescriptor,
    GeneratedMediaDescriptor,
    MediaRelationship,
    MediaAsset,
)
from video_studio.media_storage import (
    StorageTier,
    StorageSecurityViolation,
    MediaStorageManager,
    media_storage_manager,
)
from video_studio.media_probe import (
    ProbeResult,
    IMediaProbeProvider,
    BuiltinHeuristicProbeProvider,
    MediaProbeService,
    media_probe_service,
)
from video_studio.media_library import (
    MediaBinNode,
    MediaSearchQuery,
    ProjectMediaLibrary,
    MediaLibraryRegistry,
    media_library_registry,
)
from video_studio.media_preview import (
    PreviewStatus,
    ThumbnailDescriptor,
    WaveformDescriptor,
    MediaPreviewManager,
    media_preview_manager,
)
from video_studio.watch_folder import (
    WatchFolderConfig,
    WatchFolderManager,
    watch_folder_manager,
)
from video_studio.media_ingest import (
    IngestError,
    MediaIngestService,
    media_ingest_service,
)

# Module 3 Exports
from video_studio.analysis_models import (
    StreamKind,
    InterlaceMode,
    HDRStandard,
    WaveformResolution,
    ChannelMode,
    AnalysisJobStatus,
    VideoStreamDetails,
    AudioStreamDetails,
    SubtitleStreamDetails,
    ChannelWaveform,
    AudioPeakAnalysis,
    WaveformDataset,
    ThumbnailRequest,
    ContactSheetRequest,
    ContactSheetFrame,
    ContactSheetResult,
    MediaAnalysisReport,
)
from video_studio.analysis_cache import (
    MediaAnalysisCache,
    media_analysis_cache,
)
from video_studio.media_probe_engine import (
    IMediaProbeEngineProvider,
    DeepBinaryInspectionProvider,
    MediaProbeEngine,
    media_probe_engine,
)
from video_studio.thumbnail_engine import (
    ThumbnailEngine,
    thumbnail_engine,
)
from video_studio.waveform_engine import (
    WaveformEngine,
    waveform_engine,
)
from video_studio.preview_engine import (
    PreviewEngine,
    preview_engine,
)
from video_studio.analysis_jobs import (
    ResourceLimits,
    MediaAnalysisJob,
    MediaAnalysisJobManager,
    media_analysis_job_manager,
)

# Module 4 Exports
from video_studio.timeline_models import (
    TIMELINE_SCHEMA_VERSION,
    TimelineTrackType,
    TimelineItemType,
    TimelineItemState,
    MarkerCategory,
    RegionCategory,
    SourceRange,
    TimelineRange,
    SequenceSettings,
    TimelineMarker,
    TimelineRegion,
    TimelineItemModel,
    TimelineTrackModel,
    LinkGroup,
    SyncGroup,
    VideoSequence,
)
from video_studio.timeline_validation import (
    TimelineValidationError,
    TimelineValidationEngine,
    timeline_validation_engine,
)
from video_studio.timeline_query import (
    TimelineSpatialIndex,
    TimelineQueryEngine,
    timeline_query_engine,
)
from video_studio.timeline_commands import (
    TimelineOpType,
    TimelineCommand,
    TimelineTransaction,
    TimelineHistoryManager,
)
from video_studio.timeline_serialization import (
    TimelineSerializationEngine,
    timeline_serialization_engine,
)
from video_studio.timeline_service import (
    TimelineService,
    timeline_service,
)

__all__ = [
    "VideoStudioState",
    "VideoStudioMetadata",
    "VideoStudioFeatureContract",
    "VideoStudioCapabilities",
    "ComputeBackend",
    "ComputeCapabilities",
    "VideoStudioError",
    "MediaError",
    "CodecError",
    "DecodeError",
    "EncodeError",
    "RenderError",
    "GPUError",
    "AIProcessingError",
    "StorageError",
    "ExportError",
    "VideoStudioService",
    "video_studio_service",
    "VIDEO_STUDIO_CAPABILITY_CATALOG",
    "VideoStudioCategory",
    "VideoStudioCapabilityStatus",
    "ImplementationState",
    "HardwareRequirements",
    "PlatformRequirements",
    "AIRequirements",
    "CapabilityDependency",
    "CapabilityProviderDescriptor",
    "CapabilityHealthReport",
    "VideoStudioCapabilityDescriptor",
    "AccelerationAPI",
    "VideoStudioCapabilityRegistry",
    "video_studio_capability_registry",
    "VideoStudioHardwareDetector",
    "populate_roadmap_capabilities",
    # Module 2
    "AssetMediaType",
    "AssetLifecycleStatus",
    "ContainerFormat",
    "VideoCodec",
    "AudioCodec",
    "FrameRateMode",
    "MediaRelationshipType",
    "ProxyStatus",
    "RationalTime",
    "SMPTETimecode",
    "AudioStreamInfo",
    "VideoStreamInfo",
    "ProxyDescriptor",
    "GeneratedMediaDescriptor",
    "MediaRelationship",
    "MediaAsset",
    "StorageTier",
    "StorageSecurityViolation",
    "MediaStorageManager",
    "media_storage_manager",
    "ProbeResult",
    "IMediaProbeProvider",
    "BuiltinHeuristicProbeProvider",
    "MediaProbeService",
    "media_probe_service",
    "MediaBinNode",
    "MediaSearchQuery",
    "ProjectMediaLibrary",
    "MediaLibraryRegistry",
    "media_library_registry",
    "PreviewStatus",
    "ThumbnailDescriptor",
    "WaveformDescriptor",
    "MediaPreviewManager",
    "media_preview_manager",
    "WatchFolderConfig",
    "WatchFolderManager",
    "watch_folder_manager",
    "IngestError",
    "MediaIngestService",
    "media_ingest_service",
    # Module 3
    "StreamKind",
    "InterlaceMode",
    "HDRStandard",
    "WaveformResolution",
    "ChannelMode",
    "AnalysisJobStatus",
    "VideoStreamDetails",
    "AudioStreamDetails",
    "SubtitleStreamDetails",
    "ChannelWaveform",
    "AudioPeakAnalysis",
    "WaveformDataset",
    "ThumbnailRequest",
    "ContactSheetRequest",
    "ContactSheetFrame",
    "ContactSheetResult",
    "MediaAnalysisReport",
    "MediaAnalysisCache",
    "media_analysis_cache",
    "IMediaProbeEngineProvider",
    "DeepBinaryInspectionProvider",
    "MediaProbeEngine",
    "media_probe_engine",
    "ThumbnailEngine",
    "thumbnail_engine",
    "WaveformEngine",
    "waveform_engine",
    "PreviewEngine",
    "preview_engine",
    "ResourceLimits",
    "MediaAnalysisJob",
    "MediaAnalysisJobManager",
    "media_analysis_job_manager",
    # Module 4
    "TIMELINE_SCHEMA_VERSION",
    "TimelineTrackType",
    "TimelineItemType",
    "TimelineItemState",
    "MarkerCategory",
    "RegionCategory",
    "SourceRange",
    "TimelineRange",
    "SequenceSettings",
    "TimelineMarker",
    "TimelineRegion",
    "TimelineItemModel",
    "TimelineTrackModel",
    "LinkGroup",
    "SyncGroup",
    "VideoSequence",
    "TimelineValidationError",
    "TimelineValidationEngine",
    "timeline_validation_engine",
    "TimelineSpatialIndex",
    "TimelineQueryEngine",
    "timeline_query_engine",
    "TimelineOpType",
    "TimelineCommand",
    "TimelineTransaction",
    "TimelineHistoryManager",
    "TimelineSerializationEngine",
    "timeline_serialization_engine",
    "TimelineService",
    "timeline_service",
    # Module 5
    "EditConstraintViolation",
    "TimelineConstraintEngine",
    "timeline_constraint_engine",
    "StaleRevisionError",
    "TimelineEditEngine",
    "timeline_edit_engine",
    # Module 6
    "TimelineGap",
    "EditPlanPreview",
    "AdvancedTimelineEditEngine",
    "advanced_timeline_edit_engine",
    # Module 7
    "PlaybackState",
    "PlaybackQuality",
    "DecodedVideoFrame",
    "DecodedAudioBlock",
    "PlaybackMetrics",
    "PlaybackSession",
    "IMediaDecoder",
    "SoftwareMediaDecoder",
    "MediaDecoderPool",
    "decoder_pool",
    "TimelinePlaybackEngine",
    "playback_engine",
    # Module 8
    "InterpolationMode",
    "TangentType",
    "PropertyValueType",
    "KeyframeModel",
    "AnimatableProperty",
    "TransformAnimation",
    "AnimationEvaluator",
    "animation_evaluator",
    "AnimationService",
    "animation_service",
]

# Module 5 Imports
from video_studio.timeline_constraints import (
    EditConstraintViolation,
    TimelineConstraintEngine,
    timeline_constraint_engine,
)
from video_studio.timeline_edit_engine import (
    StaleRevisionError,
    TimelineEditEngine,
    timeline_edit_engine,
)

# Module 6 Imports
from video_studio.timeline_advanced_edit import (
    TimelineGap,
    EditPlanPreview,
    AdvancedTimelineEditEngine,
    advanced_timeline_edit_engine,
)

# Module 7 Imports
from video_studio.playback_models import (
    PlaybackState,
    PlaybackQuality,
    DecodedVideoFrame,
    DecodedAudioBlock,
    PlaybackMetrics,
    PlaybackSession,
)
from video_studio.playback_decoder import (
    IMediaDecoder,
    SoftwareMediaDecoder,
    MediaDecoderPool,
    decoder_pool,
)
from video_studio.playback_engine import (
    TimelinePlaybackEngine,
    playback_engine,
)

# Module 8 Imports
from video_studio.animation_models import (
    InterpolationMode,
    TangentType,
    PropertyValueType,
    KeyframeModel,
    AnimatableProperty,
    TransformAnimation,
)
from video_studio.animation_evaluator import (
    AnimationEvaluator,
    animation_evaluator,
)
from video_studio.animation_service import (
    AnimationService,
    animation_service,
)

# Module 9 Imports
from video_studio.audio_models import (
    AudioChannelLayout,
    AudioSampleFormat,
    AudioBusType,
    PanningLaw,
    SampleTime,
    AudioBuffer,
    AudioMeterSnapshot,
    AudioBus,
    AudioRoutingGraph,
    AudioDeviceDescriptor,
)
from video_studio.audio_dsp import (
    ProcessorState,
    FilterType,
    IAudioProcessor,
    GainProcessor,
    PanningProcessor,
    BiquadFilter,
    ParametricEqualizerProcessor,
    CompressorProcessor,
    ProcessorChain,
)
from video_studio.audio_mixer import (
    MultitrackAudioMixer,
    multitrack_audio_mixer,
)
from video_studio.audio_service import (
    AudioEngineService,
    audio_engine_service,
)

# Module 10 Imports
from video_studio.effects_models import (
    ParameterType,
    EffectCategory,
    ProcessingBackend,
    EffectParameterSchema,
    VideoFrameBuffer,
    EffectInstance,
    VideoEffectStack,
)
from video_studio.effects_processors import (
    IVideoEffectProcessor,
    TransformEffectProcessor,
    OpacityEffectProcessor,
    FlipEffectProcessor,
    ColorCorrectionProcessor,
    InvertEffectProcessor,
    EffectProcessorRegistry,
    effect_processor_registry,
)
from video_studio.effects_service import (
    EffectsService,
    effects_service,
)

# Module 11 Imports
from video_studio.compositing_models import (
    BlendMode,
    MaskType,
    CompositingMask,
    CompositingGroup,
    apply_blend_equation,
    composite_layers_porter_duff,
)
from video_studio.compositor import (
    MultilayerCompositor,
    multilayer_compositor,
)

# Module 12 Imports
from video_studio.transitions_models import (
    TransitionType,
    TransitionAlignment,
    TransitionDirection,
    CrossfadeCurve,
    SourceHandleValidationResult,
    VideoTransition,
)
from video_studio.transitions_engine import (
    TransitionsEngine,
    transitions_engine,
)
from video_studio.transitions_service import (
    TransitionsService,
    transitions_service,
)

# Module 13 Imports
from video_studio.captions_models import (
    SubtitleFormat,
    SubtitleAlignment,
    SubtitleVerticalPosition,
    SubtitleStyling,
    SubtitleCue,
    SubtitleDocument,
    WordTiming,
    TranscriptSegment,
    TranscriptDocument,
    SpeechToTextJob,
    TranscriptionJobStatus,
)
from video_studio.captions_formats import (
    SubtitleParser,
    SubtitleFormatError,
)
from video_studio.captions_renderer import (
    CaptionsRenderer,
    captions_renderer,
)
from video_studio.captions_service import (
    CaptionsService,
    captions_service,
    ISpeechToTextProvider,
)

# Module 14 Imports
from video_studio.motion_graphics_models import (
    GraphicLayerType,
    TextAlignment,
    TextTransformCase,
    TypographyAnimationPreset,
    GraphicTransform,
    MotionGraphicLayer,
    MotionGraphicComposition,
    MotionGraphicTemplate,
)
from video_studio.motion_graphics_renderer import (
    MotionGraphicsRenderer,
    motion_graphics_renderer,
)
from video_studio.motion_graphics_service import (
    MotionGraphicsService,
    motion_graphics_service,
)

# Module 15 Imports
from video_studio.speed_models import (
    FrameRateStandard,
    FrameInterpolationMode,
    AudioSpeedMode,
    SpeedCurveInterpolation,
    RationalTime as SpeedRationalTime,
    TimecodeConverter,
    SpeedCurvePoint,
    FreezeRegion,
    TimeRemapDocument,
)
from video_studio.speed_engine import (
    SpeedRemapEngine,
    speed_remap_engine,
)
from video_studio.speed_service import (
    SpeedService,
    speed_service,
)

# Module 16 Imports
from video_studio.color_models import (
    ColorSpace,
    ColorRange,
    LUTType,
    PrimaryGrade,
    WheelBalance,
    LiftGammaGain,
    CurvePoint,
    ColorCurves,
    HSLQualifier,
    LUTDescriptor,
    ColorGradeDocument,
    ColorScopeData,
)
from video_studio.color_lut import (
    LUTParser,
    LUTProcessor,
    lut_processor,
)
from video_studio.color_pipeline import (
    ColorPipelineProcessor,
    color_pipeline_processor,
)
from video_studio.color_service import (
    ColorService,
    color_service,
)

# Module 17 Imports
from video_studio.export_models import (
    ExportContainer,
    VideoEncoderCodec,
    AudioEncoderCodec,
    RateControlMode,
    ExportConfig,
    ExportPreset,
    RenderJobStatus,
    RenderSnapshot,
    ExportValidationReport,
    RenderJob,
)
from video_studio.export_engine import (
    ExportEngine,
    export_engine,
)
from video_studio.export_service import (
    ExportService,
    export_service,
)

# Module 18 Imports: Proxy Media, Source Selection & Media Relinking
from video_studio.proxy_models import (
    ProxyLifecycleStatus,
    ProxyProfileType,
    PlaybackSourceMode,
    ExportSourcePolicy,
    ProxyProfileConfig,
    ProxyMediaRecord,
    RelinkCandidate,
    RelinkResult,
)
from video_studio.proxy_engine import (
    ProxyEngine,
)
from video_studio.relinking_engine import (
    RelinkingEngine,
)
from video_studio.proxy_service import (
    ProxyService,
    proxy_service,
)

# Module 19 Imports: Media Transcoding, Conform & Batch Processing
from video_studio.transcode_models import (
    TranscodeJobStatus,
    BatchJobStatus,
    TranscodeContainer,
    VideoCodec,
    AudioCodec,
    ScalingPolicy,
    AudioDownmixPolicy,
    LoudnessStandard,
    DerivativeRegistrationPolicy,
    TranscodeProfile,
    ConformPlan,
    ConformTransformation,
    TranscodeJob,
    TranscodeBatchJob,
)
from video_studio.transcode_engine import (
    TranscodeEngine,
    transcode_engine,
)
from video_studio.transcode_service import (
    TranscodeService,
    transcode_service,
)

# Module 20 Imports: Multicamera Editing, Synchronization & Angle Switching
from video_studio.multicam_models import (
    CameraAngle,
    AngleSwitchDecision,
    SyncMethod,
    SyncConfidence,
    MulticamAudioPolicy,
    MulticamSequence,
    AngleSyncResult,
    MulticamFlattenResult,
)
from video_studio.multicam_sync_engine import (
    MulticamSyncEngine,
    multicam_sync_engine,
)
from video_studio.multicam_service import (
    MulticamService,
    multicam_service,
)

# Module 21 Imports: Video Stabilization, Motion Analysis & Camera Correction
from video_studio.stabilization_models import (
    MotionModelType,
    StabilizationMode,
    BorderFillMode,
    MotionTransform,
    FrameMotionRecord,
    MotionAnalysisReport,
    StabilizationConfig,
    CorrectiveTransform,
)
from video_studio.motion_analysis_engine import (
    MotionAnalysisEngine,
    motion_analysis_engine,
)
from video_studio.stabilization_engine import (
    StabilizationEngine,
    stabilization_engine,
)
from video_studio.stabilization_service import (
    StabilizationService,
    stabilization_service,
)

# Module 22 Imports: Motion Tracking, Object Tracking & Track-to-Effects
from video_studio.tracking_models import (
    TrackingMethodType,
    TrackingStatus,
    TrackTargetType,
    TrackApplicationTarget,
    TrackSample,
    TrackingSession,
    TrackToEffectBinding,
)
from video_studio.tracking_engine import (
    MotionTrackingEngine,
    motion_tracking_engine,
)
from video_studio.tracking_service import (
    TrackingService,
    tracking_service,
)

# Module 23 Imports: Green Screen, Chroma Keying & Advanced Matte Extraction
from video_studio.chroma_models import (
    ChromaColorSpace,
    ChromaKeyType,
    MatteDisplayMode,
    KeyColorSample,
    ChromaKeyConfig,
)
from video_studio.chroma_engine import (
    ChromaKeyEngine,
    chroma_key_engine,
)
from video_studio.chroma_processor import (
    ChromaKeyEffectProcessor,
)
from video_studio.chroma_service import (
    ChromaKeyService,
    chroma_key_service,
)

# Module 25 Imports: Video Denoising, Noise Reduction & Image Restoration
from video_studio.denoise_models import (
    DenoiseMethod,
    DenoiseQualityMode,
    DenoiseChannelScope,
    DenoiseConfig,
    DenoiseDiagnostics,
)
from video_studio.denoise_engine import (
    VideoDenoiseEngine,
    video_denoise_engine,
)
from video_studio.denoise_processor import (
    VideoDenoiseEffectProcessor,
)
from video_studio.denoise_service import (
    VideoDenoiseService,
    video_denoise_service,
)

# Module 26 Imports: Video Upscaling, Super-Resolution & Detail Enhancement
from video_studio.upscale_models import (
    UpscaleAlgorithm,
    SizingPolicy,
    AspectRatioMode,
    UpscaleQualityMode,
    UpscaleConfig,
    UpscaleDiagnostics,
)
from video_studio.upscale_engine import (
    VideoUpscaleEngine,
    video_upscale_engine,
)
from video_studio.upscale_processor import (
    VideoUpscaleEffectProcessor,
)
from video_studio.upscale_service import (
    VideoUpscaleService,
    video_upscale_service,
)

# Module 27 Imports: Video Frame Interpolation & Frame-Rate Conversion
from video_studio.interpolation_models import (
    InterpolationMethod,
    SceneCutAction,
    QualityMode as InterpolationQualityMode,
    RationalFrameRate,
    FrameRateConversionConfig,
    InterpolationDiagnostics,
)
from video_studio.interpolation_engine import (
    VideoInterpolationEngine,
    video_interpolation_engine,
)
from video_studio.interpolation_service import (
    VideoInterpolationService,
    video_interpolation_service,
)

# Module 28 Imports: Video Deblurring & Motion Blur Processing
from video_studio.deblur_models import (
    BlurOperationType,
    BlurKernelType,
    ShutterAngleMode,
    DeblurMethod,
    DeblurConfig,
    DeblurDiagnostics,
)
from video_studio.deblur_engine import (
    VideoDeblurEngine,
    video_deblur_engine,
)
from video_studio.deblur_processor import (
    VideoDeblurEffectProcessor,
)
from video_studio.deblur_service import (
    VideoDeblurService,
    video_deblur_service,
)

# Module 29 Imports: Video Lighting, Exposure & Relighting Engine
from video_studio.lighting_models import (
    LightType,
    LightBlendMode,
    RelightingEngineMode,
    GlobalExposureTonalConfig,
    LocalLightRegion,
    SceneAwareRelightingExtension,
    LightingEngineDocument,
    LightingDiagnostics,
)
from video_studio.lighting_engine import (
    apply_light_blend,
    VideoLightingEngine,
    video_lighting_engine,
)
from video_studio.lighting_processor import (
    VideoLightingEffectProcessor,
)
from video_studio.lighting_service import (
    VideoLightingService,
    video_lighting_service,
)

# Module 30 Imports: Video Lens Distortion & Optical Correction Engine
from video_studio.lens_models import (
    LensModelType,
    BorderHandlingMode,
    ProfileMatchBasis,
    LensProfile,
    LensCorrectionConfig,
    LensDiagnostics,
)
from video_studio.lens_engine import (
    VideoLensEngine,
    video_lens_engine,
)
from video_studio.lens_processor import (
    VideoLensEffectProcessor,
)
from video_studio.lens_service import (
    VideoLensService,
    video_lens_service,
)

# Module 31 Imports: Video Film Grain, Texture & Analog Emulation Engine
from video_studio.grain_models import (
    GrainType,
    TemporalGrainMode,
    HalationMode,
    AnalogTextureConfig,
    FilmGrainConfig,
    GrainDiagnostics,
)
from video_studio.grain_engine import (
    VideoGrainEngine,
    video_grain_engine,
)
from video_studio.grain_processor import (
    VideoGrainEffectProcessor,
)
from video_studio.grain_service import (
    VideoGrainService,
    video_grain_service,
)

# Module 32 Imports: Video Depth Estimation, Depth Maps & 2.5D Compositing Engine
from video_studio.depth_models import (
    DepthRepresentationType,
    DepthEdgeMode,
    DepthMapProvenance,
    DepthDiagnostics,
    DepthMap,
    DepthEffectConfig,
    MonocularEstimationAdapter,
)
from video_studio.depth_engine import (
    normalize_depth_map,
    generate_depth_range_mask,
    apply_depth_of_field,
    apply_parallax_25d,
    apply_depth_occlusion,
    VideoDepthEngine,
)
from video_studio.depth_processor import (
    VideoDepthEffectProcessor,
)
from video_studio.depth_service import (
    VideoDepthService,
    video_depth_service,
)

# Module 33 Imports: Optical Flow, Motion Vectors & Motion-Aware Processing Engine
from video_studio.optical_flow_models import (
    MotionVectorFieldType,
    FlowAlgorithmType,
    FlowQualityPreset,
    FlowVectorCoordinateSystem,
    FlowDirection,
    FlowFieldStatus,
    MotionVector2D,
    MotionDiagnostics,
    MotionAnalysisConfig,
    MotionVectorField,
)
from video_studio.optical_flow_engine import (
    OpticalFlowEngine,
    optical_flow_engine,
)
from video_studio.optical_flow_processor import (
    VideoMotionFlowEffectProcessor,
)
from video_studio.optical_flow_service import (
    VideoOpticalFlowService,
    video_optical_flow_service,
)

# Module 34 Imports: Object Segmentation, Semantic Masking & Subject Isolation
from video_studio.segmentation_models import (
    SegmentationWorkflowType,
    SegmentationPromptType,
    MaskCombinationMode,
    MaskFormat,
    SegmentationModelStatus,
    SegmentationPrompt,
    ModelRuntimeDescriptor,
    MaskRefinementConfig,
    VideoSegmentMask,
    MultiMaskFrameContainer,
)
from video_studio.segmentation_engine import (
    VideoSegmentationEngine,
    video_segmentation_engine,
)
from video_studio.segmentation_processor import (
    VideoSegmentationEffectProcessor,
)
from video_studio.segmentation_service import (
    VideoSegmentationService,
    video_segmentation_service,
)

# Module 35 Imports: Video Understanding, Scene Analysis & Content Intelligence
from video_studio.intelligence_models import (
    SceneBoundaryType,
    ShotTypeClassification,
    CameraMotionClassification,
    LightingClassification,
    AudioEventType,
    AnalysisSourceType,
    ShotMetadata,
    SceneMetadata,
    AudioEventSegment,
    VideoContentIntelligenceDocument,
    SemanticSearchQuery,
    SemanticSearchResult,
)
from video_studio.intelligence_engine import (
    VideoIntelligenceEngine,
    video_intelligence_engine,
)
from video_studio.intelligence_service import (
    VideoIntelligenceService,
    video_intelligence_service,
)

# Module 36 Imports: AI-Assisted Editing, Automated Rough Cut & Edit Decision Engine
from video_studio.rough_cut_models import (
    PacingProfile,
    NarrativeStructure,
    EDLApprovalStatus,
    EditingBrief,
    CandidateMoment,
    EditDecision,
    EditDecisionList,
    RoughCutResult,
)
from video_studio.rough_cut_engine import (
    RoughCutEngine,
    rough_cut_engine,
)
from video_studio.rough_cut_service import (
    RoughCutService,
    rough_cut_service,
)

# Module 37 Imports: Quality Control, Technical Validation & Delivery Compliance
from video_studio.qc_models import (
    QCReportStatus,
    QCSeverity,
    QCCategory,
    RemediabilityType,
    UserReviewStatus,
    QCInspectionScope,
    QCFinding,
    DeliveryProfile,
    QualityControlReport,
    QCJob,
    QCJobStatus,
)
from video_studio.qc_engine import (
    QualityControlEngine,
    quality_control_engine,
)
from video_studio.qc_service import (
    QualityControlService,
    quality_control_service,
)

# Module 38 Imports: Project Packaging, Media Archiving & Portable Workflow
from video_studio.package_models import (
    PACKAGE_FORMAT_VERSION,
    PackageType,
    ArchiveFormat,
    DependencyCategory,
    ExtractionPolicy,
    PackagedFileEntry,
    PackageManifest,
    ExtractionResult,
    ProjectSnapshot,
)
from video_studio.package_engine import (
    PackageEngine,
    package_engine,
    compute_sha256,
)
from video_studio.package_service import (
    PackageService,
    package_service,
)

# Module 39 Imports: Workflow Automation, Batch Operations & Editor Macros
from video_studio.workflow_models import (
    WORKFLOW_SCHEMA_VERSION,
    WorkflowExecutionState,
    StepTypeID,
    StepFailurePolicy,
    WorkflowStepDefinition,
    WorkflowDefinition,
    WorkflowStepExecutionState,
    WorkflowExecutionInstance,
    BatchExecutionResult,
)
from video_studio.workflow_engine import (
    WorkflowEngine,
    workflow_engine,
    WorkflowValidationError,
)
from video_studio.workflow_service import (
    WorkflowService,
    workflow_service,
)

# Module 40 Exports: Collaboration, Review & Annotation Engine
from video_studio.collaboration_models import (
    ParticipantRole,
    ReviewSessionStatus,
    ReviewDecisionType,
    CommentResolutionState,
    NormalizedRegion,
    ReviewComment,
    ReviewDecision,
    ReviewSession,
)
from video_studio.collaboration_engine import CollaborationEngine
from video_studio.collaboration_service import CollaborationService

# Module 41 Exports: Version Control, Branching & Non-Destructive Recovery
from video_studio.versioning_models import (
    RevisionType,
    RestoreSafetyLevel,
    StructuralDiffItem,
    RevisionDiff,
    RevisionSnapshot,
    ProjectBranch,
    RestoreResult,
    VERSION_CONTROL_SCHEMA_VERSION,
)
from video_studio.versioning_engine import VersioningEngine
from video_studio.versioning_service import (
    VersionControlService,
    version_control_service,
)

# Module 42 Exports: Media Provenance, Dependency Graph & Relinking
from video_studio.provenance_models import (
    DependencyNodeType,
    DependencyEdgeType,
    RelinkMatchConfidence,
    AssetProvenanceRecord,
    RelinkMatchCandidate,
    DependencyNode,
    DependencyEdge,
    ProjectDependencyGraph,
    RelinkTransactionResult,
    AssetUsageReport,
    PROVENANCE_SCHEMA_VERSION,
)
from video_studio.provenance_engine import (
    ProvenanceEngine,
    compute_file_sha256_chunked,
)
from video_studio.provenance_service import (
    ProvenanceService,
    provenance_service,
)

# Module 43 Exports: Media Conform, Offline Editing & Relinking
from video_studio.conform_models import (
    MediaRepresentationMode,
    ConformCompatibilityGrade,
    ProxyProfile,
    ProxyMappingRecord,
    ConformIssue,
    ConformPreflightReport,
    ConformTransactionResult,
    CONFORM_SCHEMA_VERSION,
)
from video_studio.conform_engine import ConformEngine
from video_studio.conform_service import (
    ConformService,
    conform_service,
)

# Module 44 Exports: Render Pipeline Orchestration & Fault Recovery
from video_studio.orchestration_models import (
    OrchestratedRenderState,
    VALID_STATE_TRANSITIONS,
    FailureClassification,
    RenderWorkerDescriptor,
    OrchestrationProgress,
    RenderOrchestrationJob,
    ORCHESTRATION_SCHEMA_VERSION,
)
from video_studio.orchestration_engine import OrchestrationEngine
from video_studio.orchestration_service import (
    RenderOrchestrationService,
    render_orchestration_service,
)

# Module 45 Exports: Remote Worker Protocol & Distributed Rendering
from video_studio.remote_models import (
    RemoteMessageType,
    WorkerHealthStatus,
    RemoteWorkerRegistration,
    RemoteJobAssignment,
    ChunkedAssetTransferEnvelope,
    RemoteWorkerMessage,
    REMOTE_WORKER_PROTOCOL_VERSION,
)
from video_studio.remote_engine import (
    RemoteWorkerEngine,
    hash_secret_token,
)
from video_studio.remote_service import (
    RemoteWorkerCoordinatorService,
    remote_worker_coordinator_service,
)

# Module 46 Imports: Render Farm Monitoring, Cost Attribution & Capacity Planning
from video_studio.monitoring_models import (
    MONITORING_SCHEMA_VERSION,
    OperationalAlertSeverity,
    OperationalAlertStatus,
    RenderFailureCategory,
    HardwareTelemetry,
    RenderJobTelemetryRecord,
    WorkerMonitoringSnapshot,
    QueueAnalyticsSummary,
    CostPricingModel,
    JobCostAttribution,
    CapacityForecast,
    OperationalAlert,
)
from video_studio.monitoring_engine import (
    RenderMonitoringEngine,
)
from video_studio.monitoring_service import (
    RenderMonitoringService,
    render_monitoring_service,
)




























