--[[
  download_file.lua
  Downloads a file from FILE_URL and saves it to DEST_PATH inside the repo.

  Environment variables (set by the workflow):
    FILE_URL   – direct download URL (required)
    DEST_PATH  – destination path inside the repo (optional)
                 Defaults to "uploads/<filename from URL>"
--]]

--- Exit with an error message.
local function die(msg)
  io.stderr:write("[ERROR] " .. msg .. "\n")
  os.exit(1)
end

--- Run a command; die on failure. Works with Lua 5.1 and 5.4.
local function run(cmd)
  local result = os.execute(cmd)
  -- Lua 5.4 returns true/false; Lua 5.1 returns exit code
  local ok = (result == true) or (result == 0)
  if not ok then
    die("Command failed: " .. cmd)
  end
end

--- Extract just the filename from a URL (last path segment before any ? or #).
local function filename_from_url(url)
  local name = url:match(".+/([^/?#]+)")
  if not name or name == "" then
    name = "downloaded_file"
  end
  return name
end

--- Extract the directory portion of a path.
local function dirname(path)
  return path:match("^(.*)/[^/]+$")
end

-- ── Main ─────────────────────────────────────────────────────────────────────

local file_url  = os.getenv("FILE_URL")
local dest_path = os.getenv("DEST_PATH") or ""

if not file_url or file_url == "" then
  die("FILE_URL environment variable is not set.")
end

if dest_path == "" then
  dest_path = "uploads/" .. filename_from_url(file_url)
end

print("[INFO] Source URL  : " .. file_url)
print("[INFO] Destination : " .. dest_path)

-- Create parent directory using a simple, direct approach
local dir = dirname(dest_path)
if dir and dir ~= "" then
  print("[INFO] Creating directory: " .. dir)
  -- Write dir into an env var so no quoting issues in the command
  local env = "DLDIR=" .. "'" .. dir:gsub("'", "'\\''") .. "'"
  run("env " .. env .. " bash -c 'mkdir -p \"$DLDIR\"'")
end

-- Download the file — env vars carry the values, no inline quoting needed
print("[INFO] Downloading...")
local env = "DLURL=" .. "'" .. file_url:gsub("'", "'\\''") .. "'"
         .. " DLOUT=" .. "'" .. dest_path:gsub("'", "'\\''") .. "'"
run("env " .. env .. " bash -c 'curl -L -f --progress-bar -o \"$DLOUT\" \"$DLURL\"'")

-- Sanity check
local f = io.open(dest_path, "rb")
if not f then
  die("Downloaded file not found at: " .. dest_path)
end
local size = f:seek("end")
f:close()

if size == 0 then
  die("Downloaded file is empty. The URL may not point to a real file.")
end

print(string.format("[OK] File saved to '%s' (%d bytes).", dest_path, size))