namespace MotionTrace.Core.Athletes;

public enum Joint
{
    Nose, LeftEye, RightEye, LeftEar, RightEar, LeftShoulder, RightShoulder,
    LeftElbow, RightElbow, LeftWrist, RightWrist, LeftHip, RightHip,
    LeftKnee, RightKnee, LeftAnkle, RightAnkle
}

public readonly record struct Point2(double X, double Y);
public enum TrackingState { Tracked, Lost }
public enum OcclusionRisk { Low, Medium, High }
public enum AnalysisQuality { Good, Reduced, Poor }
public sealed record Keypoint(Joint Joint, Point2 Position, double Confidence)
{
    public Point2 RawPosition { get; init; } = Position;
    public double ModelConfidence { get; init; } = Confidence;
    public double TrackingConfidence { get; init; } = 1;
    public bool IsCorrected { get; init; }
    public bool IsInterpolated { get; init; }
    public bool IsOutlier { get; init; }
}
public sealed record BoundingBox(double X, double Y, double Width, double Height);
public sealed record AthletePose(int AthleteId, BoundingBox BoundingBox, double Confidence, IReadOnlyList<Keypoint> Keypoints)
{
    public TrackingState TrackingState { get; init; }
    public OcclusionRisk OcclusionRisk { get; init; }
    public double TrackingConfidence { get; init; } = 1;
    public BoundingBox? CropBox { get; init; }
    public AnalysisQuality Quality { get; init; }
}
public sealed record ShaftSegment(double X1,double Y1,double X2,double Y2);
public sealed record ShaftObservation(int TrackId,int? AthleteId,IReadOnlyList<ShaftSegment> Segments,
    double Confidence,bool MotionReliable,double DeltaY,double DeltaSeconds);
public sealed record ObjectMeasurement(Point2 Position, string Source, AnalysisQuality Quality,
    bool IsProxy, bool IsInterpolated, bool IsManualCorrection);
public sealed record TrackedObject(string ObjectId, int? AthleteId, BoundingBox? Box, string? MaskPath,
    double Confidence, TrackingState TrackingState, ObjectMeasurement? Measurement)
{
    public string? MeasurementGroupId { get; init; }
    public int? PointIndex { get; init; }
    public string? RawObservationJson { get; init; }
}
public sealed record PoseFrame(double TimestampSeconds, IReadOnlyList<AthletePose> Athletes)
{
    public IReadOnlyList<TrackedObject> Objects { get; init; } = [];
    public ShaftObservation? Shaft { get; init; }
    public IReadOnlyList<ShaftObservation>? Shafts { get; init; }
    public IEnumerable<ShaftObservation> GetShafts() => Shafts ?? (Shaft is {} shaft ? [shaft] : []);
    public ShaftObservation? ShaftForAthlete(int athleteId) => Shafts is not null
        ? Shafts.FirstOrDefault(s => s.AthleteId == athleteId)
        : Shaft is {} shaft && (athleteId <= 0 || shaft.AthleteId is null || shaft.AthleteId == athleteId) ? shaft : null;
}
public sealed record AthleteTrack(int Id, string DisplayName)
{
    public bool IsExerciseParticipant { get; init; } = true;
}
