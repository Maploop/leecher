--[[
  download_file.lua
  -----------------
  Downloads a file from FILE_URL and saves it to DEST_PATH inside the repo.
  Called by the GitHub Actions workflow; reads configuration from environment variables.

  Environment variables (set by the workflow):
    FILE_URL   – direct download URL (required)
    DEST_PATH  – relative destination path inside the repo (optional)
                 If empty, the filename is inferred from the URL and the file
                 is placed in an "uploads/" directory at the repo root.
--]]

-- ── Helpers ──────────────────────────────────────────────────────────────────

--- Exit with an error message.
local function die(msg)
  io.stderr:write("[ERROR] " .. msg .. "\n")
  os.exit(1)
end

--- Extract the filename from a URL (last path segment, query string stripped).
local function filename_from_url(url)
  local name = url:match("/([^/?#]+)%??")
  if not name or name == "" then
    name = "downloaded_file"
  end
  return name
end

--- Extract the directory portion of a path.
local function dirname(path)
  return path:match("^(.*)/[^/]+$")
end

local function run_script(lines)
  local tmp = os.tmpname()
  local f = io.open(tmp, "w")
  if not f then die("Cannot open temp file: " .. tmp) end
  f:write("#!/bin/bash\nset -e\n")
  for _, line in ipairs(lines) do
    f:write(line .. "\n")
  end
  f:close()
  os.execute("chmod +x " .. tmp)
  local ok = os.execute(tmp)
  os.remove(tmp)
  return ok
end

--- Write arguments to a temp env file, then source it in the script.
--- This is the safest way to pass arbitrary strings (URLs, paths) to bash.
local function make_env_file(vars)
  local tmp = os.tmpname()
  local f = io.open(tmp, "w")
  if not f then die("Cannot create env file") end
  for k, v in pairs(vars) do
    -- Use printf %s to write the value verbatim into the env file
    f:write(k .. "=" .. "'" .. v:gsub("'", "'\\''") .. "'\n")
  end
  f:close()
  return tmp
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

-- Write URL and path into an env file so bash never needs to parse them inline
local env_file = make_env_file({ FILE_URL = file_url, DEST_PATH = dest_path })

-- Create parent directory
local dir = dirname(dest_path)
if dir then
  print("[INFO] Creating directory: " .. dir)
  local ok = run_script({
    ". " .. env_file,
    'mkdir -p "$(dirname "$DEST_PATH")"'
  })
  if ok ~= 0 then
    die("mkdir failed for: " .. dir)
  end
end

-- Download the file
print("[INFO] Downloading...")
local ok = run_script({
  ". " .. env_file,
  'curl -L -f -sS -o "$DEST_PATH" "$FILE_URL"'
})

os.remove(env_file)

if ok ~= 0 then
  die("curl failed. Check that FILE_URL is a valid, publicly accessible direct-download link.")
end

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