using Microsoft.UI;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Shapes;
using MotionTrace.Core.Analysis;
using MotionTrace.Core.Athletes;
using Windows.UI;

namespace motion_trace_win.Features.VideoAnalysis;

public sealed class PoseOverlayRenderer(Canvas canvas, Action<int> athleteClicked)
{
    private const double ConfidenceThreshold = 0.4;
    private static readonly Color[] Palette = [Color.FromArgb(255,185,243,105), Color.FromArgb(255,97,205,255), Color.FromArgb(255,255,183,106), Color.FromArgb(255,208,151,255)];
    private static readonly (Joint, Joint)[] Bones =
    [
        (Joint.LeftShoulder, Joint.RightShoulder), (Joint.LeftShoulder, Joint.LeftElbow), (Joint.LeftElbow, Joint.LeftWrist),
        (Joint.RightShoulder, Joint.RightElbow), (Joint.RightElbow, Joint.RightWrist), (Joint.LeftShoulder, Joint.LeftHip),
        (Joint.RightShoulder, Joint.RightHip), (Joint.LeftHip, Joint.RightHip), (Joint.LeftHip, Joint.LeftKnee),
        (Joint.LeftKnee, Joint.LeftAnkle), (Joint.RightHip, Joint.RightKnee), (Joint.RightKnee, Joint.RightAnkle),
        (Joint.Nose, Joint.LeftEye), (Joint.Nose, Joint.RightEye), (Joint.LeftEye, Joint.LeftEar), (Joint.RightEye, Joint.RightEar)
    ];

    public void Clear() => canvas.Children.Clear();

    public void Draw(PoseFrame? frame, VideoMetadata metadata, Func<int, bool> isSelected, bool debug=false, bool showPose=true)
    {
        Clear();
        if (frame is null || canvas.ActualWidth <= 0 || canvas.ActualHeight <= 0) return;
        double scale = Math.Min(canvas.ActualWidth / metadata.Width, canvas.ActualHeight / metadata.Height);
        double offsetX = (canvas.ActualWidth - metadata.Width * scale) / 2;
        double offsetY = (canvas.ActualHeight - metadata.Height * scale) / 2;
        canvas.Clip = new RectangleGeometry { Rect = new(0, 0, canvas.ActualWidth, canvas.ActualHeight) };
        foreach (var tracked in frame.Objects.Where(o => o.AthleteId is {} owner && isSelected(owner) && o.TrackingState == TrackingState.Tracked))
        {
            var brush = new SolidColorBrush(tracked.PointIndex == 1 ? Colors.Orange : tracked.Measurement?.IsProxy == true ? Colors.Goldenrod : Colors.Cyan);
            if (tracked.Box is {} objectBox)
                Place(new Rectangle { Width = objectBox.Width * scale, Height = objectBox.Height * scale,
                Stroke = brush, StrokeThickness = 2, IsHitTestVisible = false },
                offsetX + objectBox.X * scale, offsetY + objectBox.Y * scale);
            if (tracked.Measurement is {} measurement)
                Place(new Ellipse { Width = 12, Height = 12,
                    Fill = new SolidColorBrush(brush.Color) { Opacity = .35 },
                    Stroke = new SolidColorBrush(brush.Color) { Opacity = .7 },
                    StrokeThickness = 1.5, IsHitTestVisible = false },
                    offsetX + measurement.Position.X * scale - 6, offsetY + measurement.Position.Y * scale - 6);
        }
        foreach(var shaft in frame.GetShafts().Where(s=>s.AthleteId is {} owner && isSelected(owner)))
        {
            var brush=new SolidColorBrush(shaft.MotionReliable?Colors.Cyan:Colors.Goldenrod);
            foreach(var s in shaft.Segments)
                canvas.Children.Add(new Line {X1=offsetX+s.X1*scale,Y1=offsetY+s.Y1*scale,
                    X2=offsetX+s.X2*scale,Y2=offsetY+s.Y2*scale,Stroke=brush,StrokeThickness=3,IsHitTestVisible=false});

        }
        if (!showPose) return;
        foreach (var pose in frame.Athletes)
        {
            bool selected = isSelected(pose.AthleteId);
            if (!selected) continue;
            var brush = new SolidColorBrush(Palette[(pose.AthleteId - 1) % Palette.Length]);
            double x = offsetX + pose.BoundingBox.X * scale, y = offsetY + pose.BoundingBox.Y * scale;
            var box = new Rectangle { Width = pose.BoundingBox.Width * scale, Height = pose.BoundingBox.Height * scale,
                Stroke = brush, StrokeThickness = 1, Opacity = selected ? 0.65 : 0.25, IsHitTestVisible = false };
            Place(box, x, y);
            var label = new Button { Content = $"Athlete {pose.AthleteId}" + (selected ? " ✓" : "") + (pose.TrackingState==TrackingState.Lost?" · Lost":"") + (debug?$" · {pose.Quality} · {pose.TrackingConfidence:0.00}":""),
                Background = brush, Foreground = new SolidColorBrush(Colors.Black), FontSize = 11,
                Padding = new Thickness(7, 3, 7, 3), MinHeight = 24, Opacity = selected ? 1 : 0.55 };
            label.Click += (_, _) => athleteClicked(pose.AthleteId);
            Place(label, Math.Clamp(x, 0, Math.Max(0, canvas.ActualWidth - 105)), Math.Max(0, y - 27));
            ToolTipService.SetToolTip(label,$"Track {pose.AthleteId} · {pose.TrackingState}\nOcclusion: {pose.OcclusionRisk} · quality: {pose.Quality}\nTracking confidence: {pose.TrackingConfidence:0.00}");
            if (!selected || pose.TrackingState==TrackingState.Lost) continue;
            if(debug)
            {
                foreach(var point in pose.Keypoints)
                {
                    var raw=new Ellipse{Width=6,Height=6,Stroke=new SolidColorBrush(Colors.OrangeRed),StrokeThickness=1};
                    ToolTipService.SetToolTip(raw,$"{point.Joint}: model {point.ModelConfidence:0.00}, tracking {point.TrackingConfidence:0.00}\nRaw {point.RawPosition.X:0.0},{point.RawPosition.Y:0.0}\nCorrected {point.Position.X:0.0},{point.Position.Y:0.0}\nOutlier {point.IsOutlier}, interpolated {point.IsInterpolated}");
                    Place(raw,offsetX+point.RawPosition.X*scale-3,offsetY+point.RawPosition.Y*scale-3);
                }
            }
            var points = pose.Keypoints.Where(k => k.Confidence >= ConfidenceThreshold).ToDictionary(k => k.Joint);
            foreach (var (from, to) in Bones)
            {
                if (!points.TryGetValue(from, out var a) || !points.TryGetValue(to, out var b)) continue;
                canvas.Children.Add(new Line { X1 = offsetX + a.Position.X * scale, Y1 = offsetY + a.Position.Y * scale,
                    X2 = offsetX + b.Position.X * scale, Y2 = offsetY + b.Position.Y * scale,
                    Stroke = brush, StrokeThickness = 2.2, IsHitTestVisible = false });
            }
            foreach (var point in points.Values)
                Place(new Ellipse { Width = 5, Height = 5, Fill = brush, IsHitTestVisible = false },
                    offsetX + point.Position.X * scale - 2.5, offsetY + point.Position.Y * scale - 2.5);
        }
    }

    private void Place(FrameworkElement element, double x, double y)
    { Canvas.SetLeft(element, x); Canvas.SetTop(element, y); canvas.Children.Add(element); }
}
