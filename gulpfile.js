var gulp = require('gulp');
var print = require('gulp-print');
var wiredep = require('wiredep');
var inject = require('gulp-inject');
var copy = require('gulp-copy');
var flatten = require('gulp-flatten');
var angularFilesort = require('gulp-angular-filesort');
var ngAnnotate = require('gulp-ng-annotate');
var merge = require('merge-stream');
var less = require('gulp-less');
var livereload = require('gulp-livereload');
var concat = require('gulp-concat');
var sourcemaps = require('gulp-sourcemaps');
var uglify = require('gulp-uglify');
var changed = require('gulp-changed');
var newer = require('gulp-newer');
var git = require('gulp-git');
var runSequence = require('run-sequence');
var print = require('gulp-print');


gulp.task('vendor-scripts', function () {
    var dest = 'nzbhydra/static/js';
    return gulp.src(wiredep().js)
        .pipe(sourcemaps.init())
        .pipe(concat('alllibs.js'))
        .pipe(changed(dest))//Important: Put behind concat, otherwise it will always think the sources changed
        //.pipe(uglify())
        .pipe(sourcemaps.write("."))
        .pipe(gulp.dest(dest));
});

gulp.task('vendor-css', function () {
    var dest = 'nzbhydra/static/css';
    return gulp.src(wiredep().css)
        .pipe(sourcemaps.init())
        .pipe(concat('alllibs.css'))
        .pipe(changed(dest))
        .pipe(sourcemaps.write("."))
        .pipe(gulp.dest(dest));

});

gulp.task('scripts', function () {
    var dest = 'nzbhydra/static/js';
    return gulp.src("ui-src/js/**/*.js")
        .pipe(ngAnnotate())
        .on('error', swallowError)
        .pipe(angularFilesort())
        .on('error', swallowError)
        .pipe(sourcemaps.init())
        .pipe(concat('nzbhydra.js'))
        .on('error', swallowError)
        .pipe(changed(dest))
        //.pipe(uglify()) //Deactive when developing, even with source maps not nice to handle
        .pipe(sourcemaps.write('./'))
        .pipe(gulp.dest(dest));

});

gulp.task('less', function () {
    var dest = 'nzbhydra/static/css';
    gulp.src('ui-src/less/nzbhydra.less')
        .pipe(sourcemaps.init())
        .pipe(newer(dest))
        .pipe(less())
        .on('error', swallowError)
        .pipe(sourcemaps.write("."))
        .pipe(gulp.dest(dest));
});

gulp.task('copy-assets', function () {
    var fontDest = 'nzbhydra/static/fonts';
    var fonts = gulp.src("bower_components/bootstrap/fonts/*")
        .pipe(changed(fontDest))
        .pipe(gulp.dest(fontDest));

    var imgDest = 'nzbhydra/static/img';
    var img = gulp.src("ui-src/img/**/*")
        .pipe(changed(imgDest))
        .pipe(gulp.dest(imgDest));

    var htmlDest = 'nzbhydra/static/html';
    var html = gulp.src(["ui-src/html/**/*", "bower_components/angularUtils-pagination/dirPagination.tpl.html"])
        .pipe(changed(htmlDest))
        .pipe(gulp.dest(htmlDest));

    return merge(img, html, fonts);

});

gulp.task('add', function () {
    return gulp.src('nzbhydra/static/**')
        .pipe(git.add());
});

gulp.task('index', ['scripts', 'less', 'vendor-scripts', 'vendor-css', 'copy-assets'], function () {
    return gulp.src('ui-src/index.html')
        .pipe(gulp.dest('nzbhydra/templates'))
        .pipe(livereload())
        .add;
});

gulp.task('updateAdd', function() {
    runSequence('index', 'add'); 
});

function swallowError(error) {
    console.log(error.toString());
    this.emit('end');
}



gulp.task('default', function () {
    livereload.listen();
    gulp.watch(['ui-src/**/*'], ['updateAdd']);
});