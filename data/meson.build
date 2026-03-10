# Desktop integration files

install_data(
  'org.ydoit.app.desktop',
  install_dir: join_paths(get_option('datadir'), 'applications'),
)

install_data(
  'org.ydoit.app.metainfo.xml',
  install_dir: join_paths(get_option('datadir'), 'metainfo'),
)

install_data(
  'org.ydoit.app.svg',
  install_dir: join_paths(get_option('datadir'), 'icons', 'hicolor', 'scalable', 'apps'),
)

install_data(
  'org.ydoit.app-symbolic.svg',
  install_dir: join_paths(get_option('datadir'), 'icons', 'hicolor', 'symbolic', 'apps'),
)

# Optional build-time validation tests

desktop_file_validate = find_program('desktop-file-validate', required: false)
if desktop_file_validate.found()
  test('validate-desktop-file',
    desktop_file_validate,
    args: [files('org.ydoit.app.desktop')],
  )
endif

appstreamcli = find_program('appstreamcli', required: false)
if appstreamcli.found()
  test('validate-metainfo',
    appstreamcli,
    args: ['validate', '--no-net', files('org.ydoit.app.metainfo.xml')],
  )
endif
