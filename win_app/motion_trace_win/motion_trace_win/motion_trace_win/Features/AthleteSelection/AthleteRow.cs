using motion_trace_win.Shared;
using MotionTrace.Core.Athletes;

namespace motion_trace_win.Features.AthleteSelection;

public sealed class AthleteRow(int id, string displayName) : ObservableObject
{
    public int Id { get; } = id;
    public string DisplayName { get; } = displayName;
    private bool selected = true;
    public bool IsSelected { get => selected; internal set => Set(ref selected, value); }
    private string detail=$"Track {id:00} · not visible";
    public string Detail { get=>detail; private set=>Set(ref detail,value); }
    internal void UpdateTracking(AthletePose? pose) => Detail=pose is null?$"Track {Id:00} · not visible":$"Track {Id:00} · {pose.TrackingState} · {pose.Quality}";
}
