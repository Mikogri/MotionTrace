using Microsoft.UI;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Shapes;
using Microsoft.UI.Xaml.Controls;
using MotionTrace.Core.Analysis;
using MotionTrace.Core.Athletes;
using Windows.Foundation;

namespace motion_trace_win;

public sealed partial class MainWindow
{
    private Point2? trackingHover;
    private Point? trackingPanStart;
    private double trackingPanX, trackingPanY;
    private bool savingTrackingPoint;

    private void UpdateCorrectionObjects() => RefreshTrackingPoints();
    private void OnBeginCorrection(object sender, RoutedEventArgs e) => RefreshTrackingPoints();

    private Point2? CorrectionPosition(PointerRoutedEventArgs e)
    {
        if (viewModel.LoadedVideo is not {} metadata) return null;
        // GetCurrentPoint reverses the content transform before letterbox conversion.
        var position = e.GetCurrentPoint(CorrectionCanvas).Position;
        return VideoCoordinates.FromViewport(new(position.X, position.Y), CorrectionCanvas.ActualWidth,
            CorrectionCanvas.ActualHeight, metadata.Width, metadata.Height);
    }

    private async void OnCorrectionPressed(object sender, PointerRoutedEventArgs e)
    {
        if (viewModel.IsBusy) return;
        var pointer = e.GetCurrentPoint(VideoSurface);
        if (pointer.Properties.IsRightButtonPressed || pointer.Properties.IsMiddleButtonPressed)
        {
            trackingPanStart = pointer.Position;
            trackingPanX = TrackingViewportTransform.TranslateX;
            trackingPanY = TrackingViewportTransform.TranslateY;
            CorrectionCanvas.CapturePointer(e.Pointer);
            e.Handled = true;
            return;
        }
        if (!pointer.Properties.IsLeftButtonPressed || savingTrackingPoint || viewModel.TrackingPointCount >= 2 || CorrectionPosition(e) is not {} point) return;
        // Saving changes enabled buttons; keep focus on the stable video surface.
        VideoSurface.Focus(FocusState.Programmatic);
        mediaPlayer.Pause();
        double timestamp = mediaPlayer.PlaybackSession.Position.TotalSeconds;
        if (viewModel.TrackingTimestamp is {} queryTime && Math.Abs(queryTime - timestamp) > .001)
        {
            mediaPlayer.PlaybackSession.Position = TimeSpan.FromSeconds(queryTime);
            viewModel.ReportError(new InvalidOperationException("Returned to the first point's frame. Mark the second point here."));
            return;
        }
        e.Handled = true;
        savingTrackingPoint = true;
        try { await viewModel.AddTrackingPointAsync(timestamp, point); }
        catch (Exception ex) { viewModel.ReportError(ex); }
        finally { savingTrackingPoint = false; RefreshTrackingPoints(); }
    }

    private void OnCorrectionMoved(object sender, PointerRoutedEventArgs e)
    {
        if (trackingPanStart is {} start)
        {
            var current = e.GetCurrentPoint(VideoSurface).Position;
            TrackingViewportTransform.TranslateX = trackingPanX + current.X-start.X;
            TrackingViewportTransform.TranslateY = trackingPanY + current.Y-start.Y;
            ClampTrackingPan();
            e.Handled = true;
        }
        trackingHover = viewModel.TrackingPointCount < 2 && !viewModel.IsBusy ? CorrectionPosition(e) : null;
        DrawTrackingPoints();
    }

    private void OnCorrectionReleased(object sender, PointerRoutedEventArgs e)
    {
        trackingPanStart = null;
        CorrectionCanvas.ReleasePointerCaptures();
    }
    private void OnCorrectionCanceled(object sender, PointerRoutedEventArgs e) => EndCorrection();
    private void OnCorrectionExited(object sender, PointerRoutedEventArgs e) { trackingHover = null; DrawTrackingPoints(); }
    private void EndCorrection()
    {
        trackingPanStart = null;
        trackingHover = null;
        CorrectionCanvas.ReleasePointerCaptures();
        RefreshTrackingPoints();
    }

    private void RefreshTrackingPoints()
    {
        if (CorrectionCanvas is null || TrackingPointNotice is null) return;
        CorrectionCanvas.Visibility = viewModel.LoadedVideo is not null ? Visibility.Visible : Visibility.Collapsed;
        TrackingPointNotice.Visibility = viewModel.LoadedVideo is not null && !viewModel.HasTarget && !viewModel.IsAnalyzing ? Visibility.Visible : Visibility.Collapsed;
        // Once one point is placed, both queries stay on exactly the same paused frame.
        bool partial = viewModel.TrackingPointCount == 1;
        if (partial)
        {
            mediaPlayer.Pause();
            if (viewModel.TrackingTimestamp is {} queryTime && Math.Abs(mediaPlayer.PlaybackSession.Position.TotalSeconds-queryTime)>.001)
                mediaPlayer.PlaybackSession.Position = TimeSpan.FromSeconds(queryTime);
        }
        PlayButton.IsEnabled = Timeline.IsEnabled = viewModel.LoadedVideo is not null && !partial;
        if (viewModel.TrackingPointCount == 2) trackingHover = null;
        DrawTrackingPoints();
    }

    private void DrawTrackingPoints()
    {
        if (CorrectionCanvas is null || TrackingViewportTransform is null) return;
        CorrectionCanvas.ShowPointCursor(trackingHover is not null && viewModel.TrackingPointCount < 2 && !viewModel.IsBusy);
        CorrectionCanvas.Children.Clear();
        if (viewModel.LoadedVideo is not {} metadata) return;
        double scale = Math.Min(CorrectionCanvas.ActualWidth / metadata.Width, CorrectionCanvas.ActualHeight / metadata.Height);
        double ox = (CorrectionCanvas.ActualWidth - metadata.Width*scale)/2;
        double oy = (CorrectionCanvas.ActualHeight - metadata.Height*scale)/2;
        int pointIndex = 0;
        void AddDot(Point2 point, bool hover)
        {
            double diameter = (hover ? 10 : 12)/TrackingViewportTransform.ScaleX;
            var color = hover ? Colors.Orange : pointIndex++ == 0 ? Colors.Cyan : Colors.Orange;
            var dot = new Ellipse { Width = diameter, Height = diameter,
                Fill = new SolidColorBrush(color) { Opacity = .35 },
                Stroke = new SolidColorBrush(color) { Opacity = .7 },
                StrokeThickness = 1.5/TrackingViewportTransform.ScaleX, IsHitTestVisible = false };
            Canvas.SetLeft(dot, ox+point.X*scale-diameter/2);
            Canvas.SetTop(dot, oy+point.Y*scale-diameter/2);
            CorrectionCanvas.Children.Add(dot);
        }
        // Initialization dots belong to the query frame, not to every playback frame.
        if (viewModel.Result is null && (viewModel.TrackingTimestamp is not {} timestamp || Math.Abs(mediaPlayer.PlaybackSession.Position.TotalSeconds-timestamp)<.05))
            foreach (var point in viewModel.SelectedTrackingPoints) AddDot(point, false);
        if (trackingHover is {} hoverPoint) AddDot(hoverPoint, true);
    }

    private async void OnUndoTrackingPoint(object sender, RoutedEventArgs e)
    {
        VideoSurface.Focus(FocusState.Programmatic);
        mediaPlayer.Pause();
        if (viewModel.TrackingTimestamp is {} timestamp) mediaPlayer.PlaybackSession.Position = TimeSpan.FromSeconds(timestamp);
        try { await viewModel.UndoTrackingPointAsync(); } catch (Exception ex) { viewModel.ReportError(ex); }
    }
    private async void OnClearTrackingPoints(object sender, RoutedEventArgs e)
    {
        VideoSurface.Focus(FocusState.Programmatic);
        mediaPlayer.Pause();
        try { await viewModel.ClearTrackingPointsAsync(); } catch (Exception ex) { viewModel.ReportError(ex); }
    }

    private void OnTrackingWheel(object sender, PointerRoutedEventArgs e)
    {
        if (viewModel.IsBusy || viewModel.LoadedVideo is null) return;
        var point = e.GetCurrentPoint(VideoSurface);
        ZoomTrackingViewport(TrackingViewportTransform.ScaleX*Math.Pow(1.2,point.Properties.MouseWheelDelta/120d), point.Position);
        e.Handled = true;
    }
    private void OnTrackingZoomIn(object sender, RoutedEventArgs e) => ZoomTrackingViewport(TrackingViewportTransform.ScaleX*1.25);
    private void OnTrackingZoomOut(object sender, RoutedEventArgs e) => ZoomTrackingViewport(TrackingViewportTransform.ScaleX/1.25);
    private void OnTrackingZoomReset(object sender, RoutedEventArgs e) => ZoomTrackingViewport(1);
    private void ZoomTrackingViewport(double zoom, Point? anchor = null)
    {
        zoom = Math.Clamp(zoom,1,12);
        var center = anchor ?? new Point(VideoSurface.ActualWidth/2,VideoSurface.ActualHeight/2);
        double ratio = zoom/TrackingViewportTransform.ScaleX;
        TrackingViewportTransform.TranslateX = center.X-(center.X-TrackingViewportTransform.TranslateX)*ratio;
        TrackingViewportTransform.TranslateY = center.Y-(center.Y-TrackingViewportTransform.TranslateY)*ratio;
        TrackingViewportTransform.ScaleX = TrackingViewportTransform.ScaleY = zoom;
        ClampTrackingPan();
        DrawTrackingPoints();
    }
    private void ClampTrackingPan()
    {
        TrackingViewportTransform.TranslateX = Math.Clamp(TrackingViewportTransform.TranslateX, -VideoSurface.ActualWidth*(TrackingViewportTransform.ScaleX-1),0);
        TrackingViewportTransform.TranslateY = Math.Clamp(TrackingViewportTransform.TranslateY, -VideoSurface.ActualHeight*(TrackingViewportTransform.ScaleY-1),0);
        VideoSurface.Clip = new RectangleGeometry { Rect = new Rect(0,0,VideoSurface.ActualWidth,VideoSurface.ActualHeight) };
    }
}
