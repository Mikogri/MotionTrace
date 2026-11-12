using System.ComponentModel;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Controls.Primitives;
using Microsoft.UI.Xaml.Media;
using MotionTrace.Core.Analysis;
using MotionTrace.Core.Athletes;
using motion_trace_win.Features.AthleteSelection;
using motion_trace_win.Features.VideoAnalysis;
using motion_trace_win.Features.VideoImport;
using Windows.ApplicationModel.DataTransfer;
using Windows.Media.Core;
using Windows.Media.Playback;
using Windows.Storage;
using Windows.Storage.Pickers;

namespace motion_trace_win;

/// <summary>Platform file picker, media lifetime, playback controls and overlay presentation only.</summary>
public sealed partial class MainWindow : Window
{
    private readonly AnalysisViewModel viewModel;
    private MediaPlayer mediaPlayer = new() { AutoPlay = false };
    private readonly DispatcherTimer timer = new() { Interval = TimeSpan.FromMilliseconds(33) };
    private PoseOverlayRenderer? renderer;
    private PoseFrame? lastFrame;
    private bool updatingTimeline, closed;
    private MediaSource? mediaSource;
    private double sourceAspectRatio = 9.0 / 16;

    public MainWindow(AnalysisViewModel viewModel, MotionTrace.Core.Motion.IMotionTrajectoryProvider trajectoryProvider)
    {
        this.viewModel = viewModel;
        this.trajectoryProvider=trajectoryProvider;
        InitializeComponent();
        Root.DataContext = viewModel;
        RefreshProviderItems();
        ExtendsContentIntoTitleBar=false;
        LoadPhaseFilters();
        Root.ActualThemeChanged += (_, _) => { UpdateTitleColors(); UpdateAnalysisStateColor(); };
        UpdateTitleColors();
        UpdateAnalysisStateColor();
        mediaPlayer.PlaybackSession.SeekCompleted+=OnChartSeekCompleted;
        AppWindow.TitleBar.PreferredTheme = Microsoft.UI.Windowing.TitleBarTheme.UseDefaultAppMode;
        AppWindow.TitleBar.IconShowOptions = Microsoft.UI.Windowing.IconShowOptions.HideIconAndSystemMenu;
        AppWindow.SetIcon(Path.Combine(AppContext.BaseDirectory,"Assets","MotionTrace.ico"));
        AppWindow.Resize(new(1280, 860));
        if (AppWindow.Presenter is Microsoft.UI.Windowing.OverlappedPresenter presenter)
            presenter.PreferredMinimumWidth = 1000;
        Player.SetMediaPlayer(mediaPlayer);
        renderer = new(OverlayCanvas, id => { viewModel.SetSelected(id, !viewModel.IsSelected(id)); Render(force: true); });
        viewModel.PropertyChanged += OnViewModelChanged;
        mediaPlayer.MediaOpened += OnMediaOpened;
        mediaPlayer.MediaFailed += OnMediaFailed;
        timer.Tick += OnTick;
        timer.Start();
        CompositionTarget.Rendering += OnPlaybackRendering;
        Root.Loaded += OnLoaded;
        Closed += OnClosed;
    }

    private async void OnLoaded(object sender, RoutedEventArgs e)
    {
        Root.Loaded -= OnLoaded;
        UpdateWorkspaceLayout();
        var args = Environment.GetCommandLineArgs();
        var index = Array.IndexOf(args, "--video");
        if (index >= 0 && index + 1 < args.Length)
        {
            await viewModel.ImportAsync(Path.GetFullPath(args[index + 1]));
            if (args.Contains("--analyze")) await viewModel.AnalyzeAsync();
        }
        await RunComparisonSmokeAsync(args);
        await RunVideoComparisonSmokeAsync(args);
    }

    private async void OnSelectVideo(object sender, RoutedEventArgs e)
    {
        try
        {
            var picker = new FileOpenPicker();
            WinRT.Interop.InitializeWithWindow.Initialize(picker, WinRT.Interop.WindowNative.GetWindowHandle(this));
            foreach (var extension in VideoImportService.Extensions) picker.FileTypeFilter.Add(extension);
            var file = await picker.PickSingleFileAsync();
            if (file is not null && !closed) await viewModel.ImportAsync(file.Path);
        }
        catch (Exception ex) { viewModel.ReportError(ex); }
    }

    private void OnDragOver(object sender, DragEventArgs e)
    {
        e.AcceptedOperation = viewModel.CanImport && e.DataView.Contains(StandardDataFormats.StorageItems) ? DataPackageOperation.Copy : DataPackageOperation.None;
        e.DragUIOverride.Caption = "Open training video";
    }

    private async void OnDrop(object sender, DragEventArgs e)
    {
        if (!viewModel.CanImport || !e.DataView.Contains(StandardDataFormats.StorageItems)) return;
        var deferral = e.GetDeferral();
        try
        {
            var items = await e.DataView.GetStorageItemsAsync();
            if (items.Count != 1 || items[0] is not StorageFile file) throw new InvalidOperationException("Drop one video at a time.");
            if (!closed) await viewModel.ImportAsync(file.Path);
        }
        catch (Exception ex) { viewModel.ReportError(ex); }
        finally { deferral.Complete(); }
    }

    private async void OnAnalyze(object sender, RoutedEventArgs e)
    {
        if (viewModel.IsAnalyzing) { viewModel.Cancel(); return; }
        mediaPlayer.Pause();
        EndCorrection();
        await viewModel.AnalyzeAsync();
    }
    private void OnAthleteClicked(object sender, RoutedEventArgs e)
    {
        if (sender is CheckBox { DataContext: AthleteRow row } box)
        {
            viewModel.SetSelected(row.Id, box.IsChecked == true);
            box.IsChecked = row.IsSelected;
            Render(force: true);
        }
    }

    private void OnSelectAllAthletes(object sender,RoutedEventArgs e)=>viewModel.SetAllSelected(true);
    private void OnClearAllAthletes(object sender,RoutedEventArgs e)=>viewModel.SetAllSelected(false);

    private void OnChooseManualAthlete(object sender, RoutedEventArgs e)
    {
        if (!viewModel.CanChooseAthleteManually || viewModel.Result is not {} result) return;
        var choices = new MenuFlyout();
        foreach (var athlete in result.Athletes)
        {
            var item = new MenuFlyoutItem { Text = athlete.DisplayName + " · inspect for correction" };
            item.Click += (_, _) => viewModel.ChooseAthleteForCorrection(athlete.Id);
            choices.Items.Add(item);
        }
        choices.ShowAt(ChooseManualAthleteButton);
    }

    private void UpdateAnalysisStateColor()
    {
        string resource = viewModel.IsAnalyzing ? "SystemFillColorCautionBrush"
            : viewModel.NeedsReanalysis ? "SystemFillColorCautionBrush"
            : viewModel.HasResults && !viewModel.Result!.Athletes.Any(a => a.IsExerciseParticipant) ? "SystemFillColorCautionBrush"
            : viewModel.HasResults ? "SystemFillColorSuccessBrush" : "TextFillColorSecondaryBrush";
        VideoAnalysisState.Foreground = (Microsoft.UI.Xaml.Media.Brush)Application.Current.Resources[resource];
    }

    private async void OnBarbellModelChanged(object sender, SelectionChangedEventArgs e)
    {
        if (Root?.DataContext is null || updatingProviderSelector || BarbellModelSelector.SelectedIndex < 0) return;
        if (BarbellModelSelector.SelectedIndex == viewModel.SelectedBarbellModelIndex) return;
        if (MotionAthlete.SelectedItem is AthleteRow athlete) comparisonAthleteId = athlete.Id;
        comparisonRepRemapRequested = hasPresentedComparison;
        var previousResult = viewModel.Result;
        EndCorrection();
        await viewModel.SelectBarbellModelAsync(BarbellModelSelector.SelectedIndex);
        // A changed Result already applied the snapshot synchronously. Empty-to-empty selections
        // still need their own status/empty state, without rendering each ready provider twice.
        if (ReferenceEquals(previousResult, viewModel.Result)) ApplyComparisonPresentation();
    }

    private void OnViewModelChanged(object? sender, PropertyChangedEventArgs e)
    {
        if (closed) return;
        if (e.PropertyName is nameof(AnalysisViewModel.TrackingPointCount) or nameof(AnalysisViewModel.IsBusy) or nameof(AnalysisViewModel.IsAnalyzing)) RefreshTrackingPoints();
        if (e.PropertyName == nameof(AnalysisViewModel.ProviderItems)) RefreshProviderItems();
        ChooseManualAthleteButton.Visibility = viewModel.CanChooseAthleteManually ? Visibility.Visible : Visibility.Collapsed;
        if (e.PropertyName == nameof(AnalysisViewModel.AnalysisStateText)) UpdateAnalysisStateColor();
        UpdateExportState();
        if (e.PropertyName is nameof(AnalysisViewModel.IsBusy) or nameof(AnalysisViewModel.NeedsReanalysis))
        {
            if (!viewModel.IsSwitchingProvider && !initializingMotion) UpdateMovementAthleteSelection();
            lastChartRender = null;
            DrawMovement();
        }
        if (CorrectionButton is not null) CorrectionButton.IsEnabled = viewModel.CanCorrectObjects;
        if(e.PropertyName==nameof(AnalysisViewModel.SelectedAthleteCount) && !viewModel.IsSwitchingProvider)
        {
            if(MotionAthlete.SelectedItem is not AthleteRow current || !viewModel.IsSelected(current.Id))
            {
                var selected=viewModel.Athletes.FirstOrDefault(a=>viewModel.IsSelected(a.Id));
                if(selected is not null)MotionAthlete.SelectedItem=selected;
            }
            RefreshMovement();
            Render(force:true);
        }
        if (e.PropertyName == nameof(AnalysisViewModel.VideoPath))
        {
            preparedMovement = null; comparisonAthleteId = null;
            presentedProviderId = null;
            hasPresentedComparison = false; comparisonRepRemapRequested = false;
            ZoomTrackingViewport(1);
            EndCorrection();
            chartSeekInFlight=false;queuedChartSeek=null;chartDragging=false;resumeAfterChartSeek=false;
            sourceAspectRatio = viewModel.VideoAspectRatio;
            AspectRatioSelector.SelectedIndex = 0;
            UpdateWorkspaceLayout();
            OpenPlaybackVideo(viewModel.VideoPath!);
            EmptyState.Visibility = Visibility.Collapsed;
            renderer?.Clear(); lastFrame = null;
        }
        if (e.PropertyName == nameof(AnalysisViewModel.Result))
        {
            if (viewModel.Session is not null) ApplyComparisonPresentation();
            else { Render(force: true); ResetMotionSource(); }
        }
        if (e.PropertyName == nameof(AnalysisViewModel.IsAnalyzing))
            AnalysisProgressPanel.Visibility = viewModel.IsAnalyzing ? Visibility.Visible : Visibility.Collapsed;
    }

    private void OpenPlaybackVideo(string path)
    {
        // A queued event from the retired player must never mutate the new film.
        var previous = mediaPlayer;
        double volume = previous.Volume;
        bool muted = previous.IsMuted;
        previous.MediaOpened -= OnMediaOpened;
        previous.MediaFailed -= OnMediaFailed;
        previous.PlaybackSession.SeekCompleted -= OnChartSeekCompleted;
        PlayButton.IsEnabled = Timeline.IsEnabled = false;
        chartSeekInFlight = false;
        queuedChartSeek = null;
        chartDragging = resumeAfterChartSeek = false;
        Player.SetMediaPlayer(null);
        previous.Pause();
        previous.Source = null;
        previous.Dispose();
        mediaSource?.Dispose();
        mediaSource = null;
        mediaPlayer = new MediaPlayer { AutoPlay = false, Volume = volume, IsMuted = muted };
        mediaPlayer.MediaOpened += OnMediaOpened;
        mediaPlayer.MediaFailed += OnMediaFailed;
        mediaPlayer.PlaybackSession.SeekCompleted += OnChartSeekCompleted;
        Player.SetMediaPlayer(mediaPlayer);
        updatingTimeline = true;
        Timeline.Value = 0;
        updatingTimeline = false;
        mediaSource = MediaSource.CreateFromUri(new Uri(path));
        mediaPlayer.Source = mediaSource;
    }

    private void OnMediaOpened(MediaPlayer sender, object args) => DispatcherQueue.TryEnqueue(() =>
    {
        if (closed || !ReferenceEquals(sender, mediaPlayer)) return;
        var session = mediaPlayer.PlaybackSession;
        if (session.NaturalVideoWidth > 0 && session.NaturalVideoHeight > 0)
            sourceAspectRatio = (double)session.NaturalVideoWidth / session.NaturalVideoHeight;
        UpdateWorkspaceLayout();
        Timeline.Maximum = Math.Max(0.001, mediaPlayer.PlaybackSession.NaturalDuration.TotalSeconds);
        Timeline.IsEnabled = PlayButton.IsEnabled = true;
        RefreshTrackingPoints();
    });

    private void OnMediaFailed(MediaPlayer sender, MediaPlayerFailedEventArgs args) => DispatcherQueue.TryEnqueue(() =>
    {
        if (closed || !ReferenceEquals(sender, mediaPlayer)) return;
        PlayButton.IsEnabled = Timeline.IsEnabled = false;
        chartSeekInFlight = false;
        queuedChartSeek = null;
        resumeAfterChartSeek = false;
        viewModel.ReportError(new InvalidOperationException(
            $"Video playback failed for {viewModel.VideoPath}: {args.Error} (0x{args.ExtendedErrorCode?.HResult ?? 0:X8}). {args.ErrorMessage}", args.ExtendedErrorCode));
    });

    private void OnVolumeChanged(object sender, RangeBaseValueChangedEventArgs e)
    {
        mediaPlayer.Volume = Math.Clamp(e.NewValue / 100, 0, 1);
        mediaPlayer.IsMuted = false;
        UpdateVolumeDisplay();
    }
    private void UpdateVolumeDisplay()
    {
        if (VolumeIcon is null || VolumeLabel is null) return;
        bool silent = mediaPlayer.IsMuted || mediaPlayer.Volume == 0;
        VolumeIcon.Glyph = silent ? "\uE74F" : "\uE767";
        VolumeLabel.Text = silent ? "0%" : $"{mediaPlayer.Volume * 100:0}%";
    }

    private void OnPlayPause(object sender, RoutedEventArgs e)
    {
        if (mediaPlayer.PlaybackSession.PlaybackState == MediaPlaybackState.Playing) mediaPlayer.Pause();
        else mediaPlayer.Play();
    }
    private void OnSeek(object sender, RangeBaseValueChangedEventArgs e)
    {
        if (updatingTimeline || !Timeline.IsEnabled) return;
        QueueChartSeek(e.NewValue);
    }
    private void OnTick(object? sender, object e)
    {
        if (mediaPlayer.Source is null || chartSeekInFlight) return;
        updatingTimeline = true;
        Timeline.Value = mediaPlayer.PlaybackSession.Position.TotalSeconds;
        updatingTimeline = false;
        TimeLabel.Text = $"{mediaPlayer.PlaybackSession.Position:mm\\:ss} / {mediaPlayer.PlaybackSession.NaturalDuration:mm\\:ss}";
        PlayIcon.Glyph = mediaPlayer.PlaybackSession.PlaybackState == MediaPlaybackState.Playing ? "\uE769" : "\uE768";
        Render();
    }
    private void OnVideoSizeChanged(object sender, SizeChangedEventArgs e) { ClampTrackingPan(); DrawTrackingPoints(); Render(force: true); }
    private void OnVideoViewportSizeChanged(object sender, SizeChangedEventArgs e) => UpdateVideoLayout();
    private void OnAspectRatioChanged(object sender, SelectionChangedEventArgs e) => UpdateWorkspaceLayout();
    private void OnWorkspaceSizeChanged(object sender, SizeChangedEventArgs e) => UpdateWorkspaceLayout();

    private double DisplayAspectRatio => AspectRatioSelector.SelectedIndex switch
    {
        1 => 16.0 / 9,
        2 => 9.0 / 16,
        _ => sourceAspectRatio
    };

    private void UpdateWorkspaceLayout()
    {
        if (Workspace is null || VelocityColumn is null || VideoColumn is null || ResultsColumn is null ||
            LandscapeVelocityHost is null || PortraitVelocityHost is null || VelocityCard is null) return;
        bool portrait = DisplayAspectRatio < 1;
        // Portrait footage gets the full height; supporting results move beside it.
        // Reserve room for the media header/transport, then size the column to the image.

        if (portrait)
        {
            Workspace.MaxWidth = double.PositiveInfinity;
            VideoColumn.Width = new GridLength(videoWeight, GridUnitType.Star);
            VelocityColumn.Width = new GridLength(leftWeight, GridUnitType.Star);
            ResultsColumn.Width = new GridLength(rightWeight, GridUnitType.Star);
            if (LandscapeVelocityHost.Content is not null)
            {
                LandscapeVelocityHost.Content = null;
                PortraitVelocityHost.Content = VelocityCard;
            }
        }
        else
        {
            Workspace.MaxWidth = double.PositiveInfinity;
            VelocityColumn.Width = new GridLength(0);
            VideoColumn.Width = new GridLength(leftWeight+videoWeight, GridUnitType.Star);
            ResultsColumn.Width = new GridLength(rightWeight, GridUnitType.Star);
            if (PortraitVelocityHost.Content is not null)
            {
                PortraitVelocityHost.Content = null;
                LandscapeVelocityHost.Content = VelocityCard;
            }
        }
        LandscapeVelocityHost.Visibility = portrait ? Visibility.Collapsed : Visibility.Visible;
        PortraitVelocityHost.Visibility = portrait ? Visibility.Visible : Visibility.Collapsed;
        LeftDivider.Visibility=portrait?Visibility.Visible:Visibility.Collapsed;
        LayoutMotionCharts(portrait);
        UpdateVideoLayout();
    }

    private void UpdateVideoLayout()
    {
        // The player and overlay share a viewport. Uniform scaling preserves the
        // complete source frame and the renderer's existing letterbox transform.
        if (VideoViewport is null || VideoSurface is null || AspectRatioSelector is null) return;
        double ratio = DisplayAspectRatio;
        double width = Math.Min(VideoViewport.ActualWidth, VideoViewport.ActualHeight * ratio);
        VideoSurface.Width = Math.Max(0, width);
        VideoSurface.Height = Math.Max(0, width / ratio);
    }
    private void OnOverlayChanged(object sender, RoutedEventArgs e) => Render(force: true);
    private void OnPlaybackRendering(object? sender, object e)
    {
        // The video is presented independently of the slower controls timer.
        // Refresh its overlay in the same UI render cycle, using actual frame timestamps.
        if (!closed && !chartSeekInFlight && mediaPlayer.Source is not null)
            RenderOverlay();
    }
    private void Render(bool force = false)
    {
        DrawTrackingPoints();
        viewModel.UpdateExercise(mediaPlayer.PlaybackSession.Position.TotalSeconds);
        UpdateMovementPlayback();
        RenderOverlay(force);
    }
    private void RenderOverlay(bool force = false)
    {
        if (renderer is null) return;
        if (viewModel.Result is not { } result) { renderer.Clear(); lastFrame = null; return; }
        var frame = FrameLookup.At(result.Frames, mediaPlayer.PlaybackSession.Position.TotalSeconds);
        if (!force && ReferenceEquals(lastFrame, frame)) return;
        lastFrame = frame;
        renderer.Draw(frame, result.Video, viewModel.IsSelected, false, OverlayToggle.IsOn);
    }
    private void OnClosed(object sender, WindowEventArgs args)
    {
        CompositionTarget.Rendering -= OnPlaybackRendering;
        mediaPlayer.PlaybackSession.SeekCompleted-=OnChartSeekCompleted;
        closed = true; viewModel.Cancel(); timer.Stop(); timer.Tick -= OnTick;
        movementOperation?.Cancel();
        viewModel.PropertyChanged -= OnViewModelChanged;
        mediaPlayer.MediaOpened -= OnMediaOpened; mediaPlayer.MediaFailed -= OnMediaFailed;
        mediaPlayer.Source = null; Player.SetMediaPlayer(null); mediaSource?.Dispose(); mediaPlayer.Dispose();
    }
}
