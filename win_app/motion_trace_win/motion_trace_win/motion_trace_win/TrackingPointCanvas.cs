using Microsoft.UI.Input;
using Microsoft.UI.Xaml.Controls;

namespace motion_trace_win;

/// <summary>Displays the preview dot in place of the mouse arrow while marking.</summary>
public sealed class TrackingPointCanvas : Canvas
{
    private readonly InputSystemCursor arrow = InputSystemCursor.Create(InputSystemCursorShape.Arrow);
    public void ShowPointCursor(bool showPoint) => ProtectedCursor = showPoint ? null : arrow;
}
