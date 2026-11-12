using Microsoft.UI.Xaml;
using MotionTrace.Core.Analysis;
using MotionTrace.Core.Exercise;
using motion_trace_win.Features.AthleteSelection;

namespace motion_trace_win;

public sealed partial class MainWindow
{
    private PreparedMovement? preparedMovement;
    private int? comparisonAthleteId;
    private bool hasPresentedComparison;
    private string? presentedProviderId;
    private bool comparisonRepRemapRequested;
    private bool updatingProviderSelector;

    private void ApplyComparisonPresentation()
    {
        if (MotionAthlete is null || viewModel.IsSwitchingProvider) return;
        var providerId = viewModel.Session?.ActiveProviderId;
        if (hasPresentedComparison && presentedProviderId != providerId) comparisonRepRemapRequested = true;
        presentedProviderId = providerId;
        initializingMotion = true;
        try
        {
            int? ownerId = null;
            if (viewModel.Session is {} session)
            {
                using var target = System.Text.Json.JsonDocument.Parse(session.TargetJson);
                if (target.RootElement.TryGetProperty("athleteTrackId", out var owner) && owner.TryGetInt32(out int id)) ownerId = id;
            }
            MotionAthlete.SelectedItem = viewModel.Athletes.FirstOrDefault(a => a.Id == comparisonAthleteId && viewModel.IsSelected(a.Id))
                ?? viewModel.Athletes.FirstOrDefault(a => a.Id == ownerId && viewModel.IsSelected(a.Id))
                ?? viewModel.Athletes.FirstOrDefault(a => viewModel.IsSelected(a.Id))
                ?? viewModel.Athletes.FirstOrDefault();
            if (MotionAthlete.SelectedItem is AthleteRow athlete) comparisonAthleteId = athlete.Id;
            SelectDetectedExercise();
        }
        finally { initializingMotion = false; }
        UpdateCorrectionObjects();
        RefreshMovement();
        Render(force: true);
    }

    private void RefreshPreparedMovement()
    {
        ++movementRequest;
        movementOperation?.Cancel();
        var previous = preparedMovement;
        preparedMovement = null;
        movement = null; movementStates = [];
        bool fromBar = MotionSource.SelectedIndex == 1;
        MotionWrist.IsEnabled = !fromBar;
        MotionAthlete.IsEnabled = MotionAthlete.Items.Count > 0;
        MotionAthlete.PlaceholderText = MotionAthlete.Items.Count == 0 ? "No athletes available" : "Select athlete";
        var athlete = MotionAthlete.SelectedItem as AthleteRow;
        var exercise = SelectedExercise();
        if (ExerciseNotice is not null)
            ExerciseNotice.IsOpen = viewModel.ActiveSnapshot is not null && athlete is not null && viewModel.IsSelected(athlete.Id) && exercise == ExerciseType.Unknown;
        var source = fromBar ? MovementSource.Barbell : MotionWrist.SelectedIndex == 1 ? MovementSource.RightWrist : MovementSource.LeftWrist;
        if (viewModel.ActiveSnapshot is {} snapshot && athlete is not null && viewModel.IsSelected(athlete.Id))
            preparedMovement = snapshot.FindMovement(new(athlete.Id, exercise, source, MotionThreshold.Value));
        if (preparedMovement is {} prepared)
        {
            movement = prepared.Analysis;
            movementStates = prepared.States;
            MotionNote.Text = $"{viewModel.Session!.ActiveProviderId} · {movement.Note}";
            MeasurementCaption.Text = $"{movement.MeasurementSource} · px / px/s · verify against the video";
            if (!ReferenceEquals(previous, prepared))
            {
                repSelection.Reset(movement.Reps.Select(r => r.Number));
                if (comparisonRepRemapRequested)
                {
                    var match = AnalysisSession.MatchRepAt(viewModel.ActiveSnapshot!, prepared.Key, mediaPlayer.PlaybackSession.Position.TotalSeconds);
                    if (match is not null) repSelection.Activate(match.Number);
                }
                else if (movement.Reps.Count > 0)
                {
                    repSelection.Activate(movement.Reps[0].Number);
                    repSelection.SelectAll();
                }
                comparisonRepRemapRequested = false;
            }
            hasPresentedComparison = true;
        }
        else
        {
            repSelection.Reset([]);
            MeasurementCaption.Text = "No prepared measurement for this selection";
            MotionNote.Text = viewModel.ActiveSnapshot is null ? viewModel.SessionSummary
                : athlete is null ? "Select an athlete."
                : !viewModel.IsSelected(athlete.Id) ? "Select this athlete to display measurements."
                : exercise == ExerciseType.Unknown ? "Choose the exercise to display its prepared phases."
                : exercise is ExerciseType.Snatch or ExerciseType.CleanAndJerk ? "Olympic lift phases are not supported."
                : "Movement threshold changed. Analyze to prepare updated measurements for all models.";
        }
        UpdateExportState();
        BuildRepTiles();
        lastChartRender = null;
        DrawMovement();
    }

    private async void OnAnalyzeMissing(object sender, RoutedEventArgs e)
    {
        var providers = viewModel.Session?.Providers.Values.Where(p => p.Status != ProviderStatus.Ready).Select(p => p.ProviderId).ToArray();
        if (providers is { Length: 0 }) return;
        EndCorrection();
        await viewModel.RunComparisonAsync(providers);
    }

    private async void OnRetryProvider(object sender, RoutedEventArgs e)
    {
        var id = viewModel.Session?.ActiveProviderId ?? AnalysisSession.ProviderIds[viewModel.SelectedBarbellModelIndex];
        EndCorrection();
        await viewModel.RunComparisonAsync([id]);
    }

    private void RefreshProviderItems()
    {
        if (BarbellModelSelector is null) return;
        updatingProviderSelector = true;
        try
        {
            BarbellModelSelector.ItemsSource = viewModel.ProviderItems;
            BarbellModelSelector.SelectedIndex = viewModel.SelectedBarbellModelIndex;
        }
        finally { updatingProviderSelector = false; }
    }
}
