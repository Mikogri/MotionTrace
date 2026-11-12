using System.Text.Json;
using System.Text.Json.Serialization;
using MotionTrace.Core.Analysis;
using MotionTrace.Core.Athletes;
using MotionTrace.Core.Exercise;

namespace MotionTrace.Infrastructure.AI;

/// <summary>Versioned transport DTOs live at the boundary; the domain has no JSON or MMPose dependency.</summary>
public static class AnalysisJson
{
    private static readonly JsonSerializerOptions Options = new(JsonSerializerDefaults.Web)
    {
        Converters = { new JsonStringEnumConverter() }
    };

    public static async Task<AnalysisResult> ReadAsync(Stream stream, CancellationToken cancellationToken = default)
    {
        var dto = await JsonSerializer.DeserializeAsync<AnalysisDto>(stream, Options, cancellationToken)
            ?? throw new InvalidDataException("Analysis JSON is empty.");
        return Map(dto, cancellationToken);
    }

    public static Task WriteAsync(Stream stream, AnalysisResult result, CancellationToken token = default)
    {
        var video = result.Video;
        var version = result.Versions;
        var dto = new AnalysisDto(result.AnalysisSchemaVersion,
            new(video.FileName, video.DurationSeconds, video.Width, video.Height, video.FramesPerSecond),
            new(version.EngineVersion, version.PoseModelVersion, version.BarbellModelVersion, version.TrackerVersion, version.PoseModel,
                version.BarbellProvider, version.MeasurementVersion, version.CorrectionVersion),
            result.Athletes.Select(a => new AthleteDto(a.Id, a.IsExerciseParticipant, a.DisplayName)).ToArray(),
            result.Frames.Select(f => new FrameDto(f.TimestampSeconds,
                f.Athletes.Select(p => new PoseDto(p.AthleteId, Box(p.BoundingBox), p.Confidence,
                    p.Keypoints.Select(k => new KeypointDto(k.Joint, k.Position.X, k.Position.Y, k.Confidence,
                        new(k.RawPosition.X,k.RawPosition.Y),k.ModelConfidence,k.TrackingConfidence,k.IsCorrected,k.IsInterpolated,k.IsOutlier)).ToArray(),
                    p.TrackingState, p.OcclusionRisk, p.TrackingConfidence, p.CropBox is {} b ? Box(b) : null, p.Quality)).ToArray(),
                f.Shaft is {} shaft ? Shaft(shaft) : null, f.Shafts?.Select(Shaft).ToArray(),
                f.Objects.Select(o => new ObjectDto(o.ObjectId, o.AthleteId, o.Box is {} objectBox ? Box(objectBox) : null, o.MaskPath, o.Confidence, o.TrackingState,
                    o.Measurement is {} m ? new(m.Position.X, m.Position.Y, m.Source, m.Quality, m.IsProxy, m.IsInterpolated, m.IsManualCorrection) : null,
                    o.MeasurementGroupId, o.PointIndex,
                    o.RawObservationJson is {} raw ? JsonSerializer.Deserialize<JsonElement>(raw) : null)).ToArray())).ToArray(),
            result.Limitations.ToArray(), result.ExercisePredictions.Select(p => new ExercisePredictionDto(p.AthleteId,
                p.Exercise, p.Score, p.Margin, p.Windows.Select(w => new ExerciseWindowDto(w.StartSeconds, w.EndSeconds,
                    w.Scores.ToDictionary(), w.Decision, w.PromptLogits.ToArray(), w.SampleTimestamps.ToArray(), w.Score, w.Margin, w.Reason)).ToArray(),
                p.Method, p.Aggregation, p.ScoreMeaning, p.ModelExercise, p.OwnershipGate)).ToArray(),
            result.VisionMetadataJson is {} metadata ? JsonSerializer.Deserialize<JsonElement>(metadata) : null, result.VideoHash);
        return JsonSerializer.SerializeAsync(stream, dto, Options, token);
        static BoxDto Box(BoundingBox b) => new(b.X, b.Y, b.Width, b.Height);
        static ShaftDto Shaft(ShaftObservation s) => new(s.TrackId, s.AthleteId, s.Segments.Select(l =>
            new ShaftSegmentDto(l.X1, l.Y1, l.X2, l.Y2)).ToArray(), s.Confidence, s.MotionReliable, s.DeltaY, s.DeltaSeconds);
    }

    public static AnalysisResult Map(AnalysisDto dto, CancellationToken cancellationToken = default)
    {
        if (dto.SchemaVersion is not (1 or 2 or 3 or 4)) throw new InvalidDataException($"Unsupported analysis schema: {dto.SchemaVersion}.");
        if (dto.Video is not { } v || string.IsNullOrWhiteSpace(v.FileName) || v.Width <= 0 || v.Height <= 0 ||
            !Positive(v.DurationSeconds) || !Positive(v.FramesPerSecond)) throw new InvalidDataException("Invalid video metadata.");
        if (dto.Versions is not { } versions || string.IsNullOrWhiteSpace(versions.EngineVersion) ||
            string.IsNullOrWhiteSpace(versions.PoseModelVersion) || string.IsNullOrWhiteSpace(versions.BarbellModelVersion))
            throw new InvalidDataException("Analysis version metadata is missing.");
        if (dto.Athletes is null || dto.Frames is null || dto.Limitations is null) throw new InvalidDataException("Missing analysis collections.");
        var ids = new HashSet<int>();
        var athletes = dto.Athletes.Select(a =>
        {
            if (a is null || a.Id <= 0 || !ids.Add(a.Id)) throw new InvalidDataException("Invalid or duplicate athlete ID.");
            return new AthleteTrack(a.Id, string.IsNullOrWhiteSpace(a.DisplayName) ? $"Athlete {a.Id}" : a.DisplayName) { IsExerciseParticipant = a.IsExerciseParticipant };
        }).ToArray();
        double previousTime = -1;
        var objectOwners = new Dictionary<string, int?>();
        var pointIdentities = new Dictionary<string, (string?, int?)>();
        var frames = new List<PoseFrame>(dto.Frames.Length);
        foreach (var frame in dto.Frames)
        {
            cancellationToken.ThrowIfCancellationRequested();
            if (frame is null) throw new InvalidDataException("Null frame.");
            if (!double.IsFinite(frame.TimestampSeconds) || frame.TimestampSeconds <= previousTime || frame.TimestampSeconds < 0 ||
                frame.TimestampSeconds > v.DurationSeconds + 0.1 || frame.Athletes is null) throw new InvalidDataException("Invalid frame timestamp or poses.");
            previousTime = frame.TimestampSeconds;
            var frameIds = new HashSet<int>();
            var poses = frame.Athletes.Select(p =>
            {
                if (p is null || !ids.Contains(p.AthleteId) || !frameIds.Add(p.AthleteId) || !Confidence(p.Confidence) ||
                    p.BoundingBox is not { } b || !double.IsFinite(b.X) || !double.IsFinite(b.Y) || !Positive(b.Width) || !Positive(b.Height) || p.Keypoints is null)
                    throw new InvalidDataException("Invalid athlete pose.");
                var joints = new HashSet<Joint>();
                var points = p.Keypoints.Select(k =>
                {
                    if (k is null || !Enum.IsDefined(k.Joint) || !joints.Add(k.Joint) || !double.IsFinite(k.X) || !double.IsFinite(k.Y) || !Confidence(k.Confidence))
                        throw new InvalidDataException("Invalid keypoint.");
                    if ((k.RawPosition is {} raw && (!double.IsFinite(raw.X) || !double.IsFinite(raw.Y))) ||
                        (k.ModelConfidence is {} modelConfidence && !Confidence(modelConfidence)) ||
                        (k.TrackingConfidence is {} trackingConfidence && !Confidence(trackingConfidence)))
                        throw new InvalidDataException("Invalid corrected keypoint metadata.");
                    return new Keypoint(k.Joint, new(k.X, k.Y), k.Confidence) { RawPosition=k.RawPosition is {} original ? new(original.X,original.Y) : new(k.X,k.Y),
                        ModelConfidence=k.ModelConfidence ?? k.Confidence,TrackingConfidence=k.TrackingConfidence ?? 1,
                        IsCorrected=k.IsCorrected,IsInterpolated=k.IsInterpolated,IsOutlier=k.IsOutlier };
                }).ToArray();
                if (!Enum.IsDefined(p.TrackingState) || !Enum.IsDefined(p.OcclusionRisk) || !Enum.IsDefined(p.Quality) || !Confidence(p.TrackingConfidence)) throw new InvalidDataException("Invalid tracking metadata.");
                if(p.CropBox is {} crop && (!double.IsFinite(crop.X) || !double.IsFinite(crop.Y) || !Positive(crop.Width) || !Positive(crop.Height))) throw new InvalidDataException("Invalid crop box.");
                return new AthletePose(p.AthleteId, new(b.X, b.Y, b.Width, b.Height), p.Confidence, points)
                {
                    TrackingState=p.TrackingState, OcclusionRisk=p.OcclusionRisk, TrackingConfidence=p.TrackingConfidence, Quality=p.Quality,
                    CropBox=p.CropBox is {} c ? new(c.X,c.Y,c.Width,c.Height) : null
                };
            }).ToArray();
            if (frame.Shafts is not null && frame.Shaft is not null)
                throw new InvalidDataException("Ambiguous shaft representations.");
            var trackIds = new HashSet<int>();
            var owners = new HashSet<int>();
            ShaftObservation MapShaft(ShaftDto s)
            {
                if (s is null || !trackIds.Add(s.TrackId) || (s.AthleteId is {} id && !owners.Add(id)))
                    throw new InvalidDataException("Null or duplicate shaft track/owner.");
                if(s.TrackId<=0 || (s.AthleteId is {} owner && !ids.Contains(owner)) || !Confidence(s.Confidence) ||
                    !double.IsFinite(s.DeltaY) || !double.IsFinite(s.DeltaSeconds) || s.DeltaSeconds<0 ||
                    (s.MotionReliable && (s.DeltaSeconds<=0 || s.DeltaSeconds>.15)) || s.Segments is null || s.Segments.Length==0)
                    throw new InvalidDataException("Invalid shaft observation.");
                foreach(var line in s.Segments)
                    if(line is null || !Coordinate(line.X1,v.Width) || !Coordinate(line.X2,v.Width) ||
                        !Coordinate(line.Y1,v.Height) || !Coordinate(line.Y2,v.Height))
                        throw new InvalidDataException("Invalid shaft segment.");
                return new(s.TrackId,s.AthleteId,s.Segments.Select(l=>new ShaftSegment(l.X1,l.Y1,l.X2,l.Y2)).ToArray(),
                    s.Confidence,s.MotionReliable,s.DeltaY,s.DeltaSeconds);
            }
            var shafts = frame.Shafts?.Select(MapShaft).ToArray();
            var shaft = frame.Shaft is {} legacy ? MapShaft(legacy) : null;
            var objectIds = new HashSet<string>();
            var objects = (frame.Objects ?? []).Select(o =>
            {
                if (o is null || string.IsNullOrWhiteSpace(o.ObjectId) || !objectIds.Add(o.ObjectId) ||
                    (o.AthleteId is {} owner && !ids.Contains(owner)) || !Confidence(o.Confidence) ||
                    !Enum.IsDefined(o.TrackingState) || (o.TrackingState == TrackingState.Tracked && o.Box is null &&
                        o.Measurement is not { IsProxy: false, Source: "tapnextpp" or "bootstapir" }))
                    throw new InvalidDataException("Invalid tracked object.");
                if (o.Box is {} box && (!Coordinate(box.X, v.Width) || !Coordinate(box.Y, v.Height) ||
                    !Positive(box.Width) || !Positive(box.Height) || box.X + box.Width > v.Width + .001 || box.Y + box.Height > v.Height + .001))
                    throw new InvalidDataException("Invalid object box.");
                if (objectOwners.TryGetValue(o.ObjectId, out var priorOwner) && priorOwner != o.AthleteId)
                    throw new InvalidDataException("Object changed athlete ownership.");
                objectOwners[o.ObjectId] = o.AthleteId;
                if ((o.MeasurementGroupId is null) != (o.PointIndex is null) ||
                    (o.MeasurementGroupId is not null && (string.IsNullOrWhiteSpace(o.MeasurementGroupId) || o.PointIndex is not (0 or 1))) ||
                    (pointIdentities.TryGetValue(o.ObjectId, out var identity) && identity != (o.MeasurementGroupId, o.PointIndex)))
                    throw new InvalidDataException("Invalid or changed tracking point identity.");
                pointIdentities[o.ObjectId] = (o.MeasurementGroupId, o.PointIndex);
                ObjectMeasurement? measurement = null;
                if (o.Measurement is {} m)
                {
                    if (o.TrackingState == TrackingState.Lost || !Coordinate(m.X, v.Width) || !Coordinate(m.Y, v.Height) ||
                        string.IsNullOrWhiteSpace(m.Source) || !Enum.IsDefined(m.Quality) ||
                        (m.Source == "mask-proxy" && !m.IsProxy))
                        throw new InvalidDataException("Invalid object measurement.");
                    measurement = new(new(m.X, m.Y), m.Source, m.Quality, m.IsProxy, m.IsInterpolated, m.IsManualCorrection);
                }
                return new TrackedObject(o.ObjectId, o.AthleteId, o.Box is {} b ? new(b.X, b.Y, b.Width, b.Height) : null,
                    o.MaskPath, o.Confidence, o.TrackingState, measurement)
                    { MeasurementGroupId = o.MeasurementGroupId, PointIndex = o.PointIndex, RawObservationJson = o.RawObservation?.GetRawText() };
            }).ToArray();
            foreach (var group in objects.Where(o => o.MeasurementGroupId is not null).GroupBy(o => o.MeasurementGroupId))
                if (group.Count() != 2 || group.Select(o => o.PointIndex).Distinct().Count() != 2 ||
                    group.Select(o => o.AthleteId).Distinct().Count() != 1)
                    throw new InvalidDataException("A measurement pair requires two distinct points with the same owner.");
            frames.Add(new(frame.TimestampSeconds, poses) { Shaft=shaft, Shafts=shafts, Objects=objects });
        }
        var predictionIds = new HashSet<int>();
        var predictions = (dto.ExercisePredictions ?? []).Select(p =>
        {
            if (p is null || !ids.Contains(p.AthleteId) || !predictionIds.Add(p.AthleteId) || !Enum.IsDefined(p.Exercise) ||
                !Confidence(p.Score) || !double.IsFinite(p.Margin) || p.Margin is < -1 or > 1 ||
                string.IsNullOrWhiteSpace(p.Method) || p.Windows is null ||
                (p.ModelExercise is {} modelExercise && !Enum.IsDefined(modelExercise)))
                throw new InvalidDataException("Invalid exercise prediction.");
            foreach (var window in p.Windows)
                if (window is null || !double.IsFinite(window.StartSeconds) || !double.IsFinite(window.EndSeconds) ||
                    window.StartSeconds < 0 || window.EndSeconds <= window.StartSeconds || window.EndSeconds > v.DurationSeconds + .1 ||
                    !Enum.IsDefined(window.Decision) || window.Scores is null || window.Scores.Any(s => !double.IsFinite(s.Value)) ||
                    (window.PromptLogits?.Any(s => !double.IsFinite(s)) ?? false) ||
                    (window.SampleTimestamps?.Any(s => s is {} t && (!double.IsFinite(t) || t < 0 || t > v.DurationSeconds + .1)) ?? false) ||
                    !double.IsFinite(window.Score) || !double.IsFinite(window.Margin))
                    throw new InvalidDataException("Invalid exercise window.");
            return new ExercisePrediction(p.AthleteId, p.Exercise, p.Score, p.Margin, p.Windows.Select(w =>
                new ExerciseWindow(w.StartSeconds, w.EndSeconds, w.Scores, w.Decision) { PromptLogits=w.PromptLogits ?? [],
                    SampleTimestamps=w.SampleTimestamps ?? [], Score=w.Score, Margin=w.Margin, Reason=w.Reason }).ToArray(), p.Method)
                { Aggregation=p.Aggregation, ScoreMeaning=p.ScoreMeaning, ModelExercise=p.ModelExercise, OwnershipGate=p.OwnershipGate };
        }).ToArray();
        return new(dto.SchemaVersion, new(v.FileName, v.DurationSeconds, v.Width, v.Height, v.FramesPerSecond),
            new(versions.EngineVersion, versions.PoseModelVersion, versions.BarbellModelVersion) { TrackerVersion=versions.TrackerVersion, PoseModel=versions.PoseModel,
                BarbellProvider=versions.BarbellProvider, MeasurementVersion=versions.MeasurementVersion, CorrectionVersion=versions.CorrectionVersion }, athletes, frames, dto.Limitations)
        { ExercisePredictions = predictions, VisionMetadataJson = dto.VisionMetadata?.GetRawText(), VideoHash = dto.VideoHash };
    }

    private static bool Positive(double value) => double.IsFinite(value) && value > 0;
    private static bool Coordinate(double value,double maximum)=>double.IsFinite(value) && value>=0 && value<=maximum;
    private static bool Confidence(double value) => double.IsFinite(value) && value is >= 0 and <= 1;
}

public sealed record AnalysisDto(int SchemaVersion, VideoDto Video, VersionsDto Versions, AthleteDto[] Athletes, FrameDto[] Frames, string[] Limitations,
    ExercisePredictionDto[]? ExercisePredictions = null, JsonElement? VisionMetadata = null, string? VideoHash = null);
public sealed record VideoDto(string FileName, double DurationSeconds, int Width, int Height, double FramesPerSecond);
public sealed record VersionsDto(string EngineVersion, string PoseModelVersion, string BarbellModelVersion, string TrackerVersion="legacy", string PoseModel="unspecified",
    string? BarbellProvider=null, string? MeasurementVersion=null, string CorrectionVersion="none");
public sealed record AthleteDto(int Id, bool IsExerciseParticipant=true, string? DisplayName=null);
public sealed record FrameDto(double TimestampSeconds, PoseDto[] Athletes, ShaftDto? Shaft=null, ShaftDto[]? Shafts=null, ObjectDto[]? Objects=null);
public sealed record ObjectDto(string ObjectId, int? AthleteId, BoxDto? Box, string? MaskPath, double Confidence,
    TrackingState TrackingState, MeasurementDto? Measurement, string? MeasurementGroupId=null, int? PointIndex=null,
    JsonElement? RawObservation=null);
public sealed record MeasurementDto(double X, double Y, string Source, AnalysisQuality Quality,
    bool IsProxy, bool IsInterpolated, bool IsManualCorrection);
public sealed record ExercisePredictionDto(int AthleteId, ExerciseType Exercise, double Score, double Margin,
    ExerciseWindowDto[] Windows, string Method, string? Aggregation=null, string? ScoreMeaning=null,
    ExerciseType? ModelExercise=null, string? OwnershipGate=null);
public sealed record ExerciseWindowDto(double StartSeconds, double EndSeconds, Dictionary<string, double> Scores, ExerciseType Decision,
    double[]? PromptLogits=null, double?[]? SampleTimestamps=null, double Score=0, double Margin=0, string? Reason=null);
public sealed record ShaftDto(int TrackId,int? AthleteId,ShaftSegmentDto[] Segments,double Confidence,bool MotionReliable,double DeltaY,double DeltaSeconds);
public sealed record ShaftSegmentDto(double X1,double Y1,double X2,double Y2);
public sealed record PoseDto(int AthleteId, BoxDto BoundingBox, double Confidence, KeypointDto[] Keypoints,
    TrackingState TrackingState=TrackingState.Tracked, OcclusionRisk OcclusionRisk=OcclusionRisk.Low, double TrackingConfidence=1, BoxDto? CropBox=null,
    AnalysisQuality Quality=AnalysisQuality.Good);
public sealed record BoxDto(double X, double Y, double Width, double Height);
public sealed record PointDto(double X, double Y);
public sealed record KeypointDto(Joint Joint, double X, double Y, double Confidence, PointDto? RawPosition=null,
    double? ModelConfidence=null, double? TrackingConfidence=null, bool IsCorrected=false, bool IsInterpolated=false, bool IsOutlier=false);
