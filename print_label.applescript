on run argv
    set labelPath to item 1 of argv

    -- Open exactly like a double-click (label is pre-patched for 24mm tape)
    do shell script "open " & quoted form of labelPath

    -- Wait for P-touch Editor to load the document
    delay 2

    tell application "P-touch Editor"
        activate
    end tell
    delay 0.5

    tell application "System Events"
        tell process "P-touch Editor"
            -- Send Cmd+P then confirm print dialog
            keystroke "p" using command down
            delay 2
            key code 36
        end tell
    end tell
end run
